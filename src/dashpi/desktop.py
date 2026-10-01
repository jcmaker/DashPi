"""Native Qt Widgets controls for the Raspberry Pi display."""

from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
import faulthandler
import json
import logging
import math
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import secrets
import shutil
import sys
import threading
import time
from collections import deque

from PySide6.QtCore import Qt, QtMsgType, QLockFile, QPointF, QRect, QRectF, QTimer, QUrl, QSize, qInstallMessageHandler
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QScrollArea, QScroller,
    QSizePolicy,
    QStackedWidget, QStyle, QStyleOptionToolButton, QStylePainter, QToolButton, QVBoxLayout, QWidget,
)

from dashpi.analysis import api_key_configured, build_analyzer
from dashpi.analysis_retry import AnalysisRetrier
from dashpi.analysis_worker import AnalysisWorker
from dashpi.config import Settings
from dashpi.device import VideoSettings, load_settings, save_settings
from dashpi.device_session import DeviceSession
from dashpi.models import IncidentState
from dashpi import progress
from dashpi.offline_video import analyze_external_video
from dashpi.optical.container import MAX_PAYLOAD
from dashpi.optical.session import OpticalSession
from dashpi.pi_camera import PiCameraRecorder
from dashpi.pipeline import IncidentPipeline
from dashpi.ranges import _open_verified_file
from dashpi.storage import IncidentStore
from dashpi import theme


log = logging.getLogger("dashpi")


def setup_logging(root: Path) -> Path:
    """Daily log files under <data root>/logs so a reported time can be matched to what happened."""
    directory = root / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(directory / "dashpi.log", when="midnight", backupCount=14,
                                       encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)

    def uncaught(kind, value, traceback):
        log.critical("처리되지 않은 오류", exc_info=(kind, value, traceback))
        sys.__excepthook__(kind, value, traceback)

    sys.excepthook = uncaught
    threading.excepthook = lambda args: log.critical(
        "스레드 오류", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    faulthandler.enable(open(directory / "crash.log", "a"))  # native crashes (segfaults) in Qt/camera code

    def qt_message(kind, _context, message):
        if kind in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            log.warning("Qt: %s", message)

    qInstallMessageHandler(qt_message)
    return directory


STATE_LABELS = {
    IncidentState.COLLECTING_POST_TRIGGER: "수집 중",
    IncidentState.CLIPPING: "영상 저장 중",
    IncidentState.ANALYZING: "분석 중",
    IncidentState.AWAITING_ANALYSIS: "분석 대기",
    IncidentState.READY: "분석 완료",
    IncidentState.CLIP_FAILED: "영상 저장 실패",
    IncidentState.ANALYSIS_FAILED: "분석 실패",
}


def local_time(iso: str) -> str:
    """'2026-09-24T14:13:03+00:00' -> '9월 24일 23:13' in the Pi's local time zone."""
    try:
        moment = datetime.fromisoformat(iso).astimezone()
    except ValueError:
        return iso
    return f"{moment.month}월 {moment.day}일 {moment:%H:%M}"


def button(text: str, callback, *, primary: bool = False) -> QPushButton:
    result = QPushButton(text)
    result.setMinimumHeight(64)
    if primary:
        result.setObjectName("primary")
    result.clicked.connect(lambda: log.info("버튼: %s", text))
    result.clicked.connect(callback)
    return result


def back_button(callback) -> QToolButton:
    """Top-left back arrow: a full-width 뒤로 row cost a whole button's height on the 480px LCD."""
    result = QToolButton()
    result.setObjectName("back")
    result.setAccessibleName("뒤로")
    left = theme.icon("chevron-down").pixmap(64, 64).transformed(QTransform().rotate(90))
    result.setIcon(QIcon(left))
    result.setIconSize(QSize(28, 28))
    result.setFixedSize(48, 48)
    result.clicked.connect(lambda: log.info("버튼: 뒤로"))
    result.clicked.connect(callback)
    return result


def page(title: str, back=None) -> tuple[QWidget, QVBoxLayout]:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(24, 20, 24, 20)
    layout.setSpacing(14)
    heading = QLabel(title)
    heading.setObjectName("title")
    if back is None:
        layout.addWidget(heading)
    else:
        header = QHBoxLayout()
        header.setSpacing(6)
        header.addWidget(back_button(back), 0, Qt.AlignmentFlag.AlignLeft)  # stays left even when the title is hidden
        header.addWidget(heading, 1)
        layout.addLayout(header)
    widget.heading = heading
    return widget, layout


class HomeTile(QToolButton):
    """Fills its share of the screen; the icon follows the tile so small LCDs and big displays both work."""

    def resizeEvent(self, event):
        side = min(96, int(min(self.width(), self.height()) * 0.35))  # 96px = bundled icon resolution
        self.setIconSize(QSize(side, side))
        super().resizeEvent(event)

    def paintEvent(self, event):
        # QToolButton pins the icon to the top; draw icon + label as one centered group instead.
        option = QStyleOptionToolButton()
        self.initStyleOption(option)
        option.text, option.icon = "", QIcon()
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ToolButton, option)
        side, line = self.iconSize().height(), self.fontMetrics().height()
        top = (self.height() - side - side // 4 - line) // 2
        self.icon().paint(painter, QRect((self.width() - side) // 2, top, side, side))
        painter.drawText(QRect(0, top + side + side // 4, self.width(), line),
                         Qt.AlignmentFlag.AlignCenter, self.text())


ANALYSIS_STEPS = (
    ("clip", "사고 구간 잘라 봉인"),
    ("frames", "영상 지문 확인 · 사진 뽑기"),
    ("locate", "AI · 사고 순간 찾기"),
    ("observe", "AI · 사고 전후 자세히 보기"),
    ("report", "AI · 요약 작성"),
    ("build", "리포트 만들기"),
)
# What each model call is actually asked (see analysis.py), shown while the driver waits.
AI_ASKS = {
    "locate": "사진 12장에서 충돌·급정거·급회피가 일어난 순간을 찾고 있어요",
    "observe": "사고 전후 3초의 차량·보행자·신호·차선을 보이는 그대로 적고 있어요",
    "report": "관찰 기록만 근거로 운전자가 읽을 요약을 쓰고 있어요",
}


class StepIcon(QWidget):
    """Ring, spinning arc, check, dash or cross for one analysis step."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(24, 24)
        self.state, self.angle = "pending", 0

    def paintEvent(self, _event):
        colors = theme.TOKENS
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        circle = QRectF(3, 3, 18, 18)

        def pen(color, width=2.4):
            result = QPen(QColor(color), width)
            result.setCapStyle(Qt.PenCapStyle.RoundCap)
            return result

        if self.state == "start":
            painter.setPen(pen(colors["stroke_top"]))
            painter.drawEllipse(circle)
            painter.setPen(pen(colors["accent"]))
            painter.drawArc(circle, -self.angle * 16, 100 * 16)
        elif self.state in ("done", "fail"):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(colors["accent" if self.state == "done" else "critical"]))
            painter.drawEllipse(circle)
            painter.setPen(pen("#ffffff", 2.2))
            if self.state == "done":
                painter.drawPolyline([QPointF(7.5, 12.5), QPointF(10.5, 15.5), QPointF(16.5, 9)])
            else:
                painter.drawLine(QPointF(8.5, 8.5), QPointF(15.5, 15.5))
                painter.drawLine(QPointF(15.5, 8.5), QPointF(8.5, 15.5))
        elif self.state == "skip":
            painter.setPen(pen(colors["text_disabled"]))
            painter.drawLine(QPointF(7, 12), QPointF(17, 12))
        else:
            painter.setPen(pen(colors["stroke_top"]))
            painter.drawEllipse(circle)


def home_tile(text: str, icon: QIcon, callback, *, primary: bool = False) -> QToolButton:
    result = HomeTile()
    result.setText(text)
    result.setIcon(icon)
    result.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    result.setMinimumSize(120, 140)  # smallest comfortable touch target; 3 tiles fit 480px wide
    result.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    if primary:
        result.setObjectName("primary")
    result.clicked.connect(lambda: log.info("버튼: %s", text))
    result.clicked.connect(callback)
    return result


class DashPiWindow(QMainWindow):
    def __init__(self, session: DeviceSession, store: IncidentStore, settings_path: Path):
        super().__init__()
        self.session, self.store, self.settings_path = session, store, settings_path
        self.setWindowTitle("DashPi")
        self.resize(1024, 600)
        theme.apply(QApplication.instance())
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dashpi-camera")
        self._jobs: list[tuple[Future, object]] = []
        self._tick_future: Future | None = None
        self._close_when_done = False
        self._starting = False
        self._recording_mode = "drive"
        self._preview_widget = None
        self._tracking_overlay_visible = False
        self._tracking_error_reported = None
        self._tracking_overlay_failed = False
        self.optical_session: OpticalSession | None = None
        self._optical_sequence = 0
        self._optical_generation = 0
        self._selected_incident = None
        self._selected_external: Path | None = None
        self._detail_generation = 0
        self.pages = QStackedWidget()
        self.pages.currentChanged.connect(
            lambda index: log.info("화면: %s", self.pages.widget(index).heading.text())
        )
        self.setCentralWidget(self.pages)

        self._build_home()
        self._build_confirmation()
        self._build_recording()
        self._build_records()
        self._build_settings()
        self._build_detail()
        self._build_optical()
        self._build_analysis()
        self.show_home()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(100)
        self.retrier = None
        if hasattr(self.session, "worker") and hasattr(self.session, "settings"):
            self.retrier = AnalysisRetrier(self.store, self._run_retry)
            self.retry_timer = QTimer(self)
            self.retry_timer.timeout.connect(self._retry_tick)
            self.retry_timer.start(60_000)
            QTimer.singleShot(0, self._start_retries)
        self.optical_timer = QTimer(self)
        self.optical_timer.timeout.connect(self._render_optical_frame)
        self.showFullScreen()

    def _build_home(self):
        self.home, layout = page("DashPi")
        row = QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(home_tile("녹화기록", theme.icon("folder"), self.show_records))
        row.addWidget(home_tile("주행시작", theme.icon("record"), self.show_start_confirmation,
                                primary=True))
        row.addWidget(home_tile("설정", theme.icon("settings"), self.show_settings))
        layout.addLayout(row, 1)
        self.home_status = QLabel("")
        self.home_status.setObjectName("caption")
        self.home_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.home_status.setWordWrap(True)
        layout.addWidget(self.home_status)
        self.pages.addWidget(self.home)

    def _build_confirmation(self):
        self.confirmation, layout = page("녹화 시작", back=self.show_home)
        description = QLabel("카메라로 영상을 기록합니다. 주행 또는 수동 주차 녹화를 선택하세요.")
        description.setObjectName("caption")
        layout.addWidget(description)
        layout.addWidget(button("주행 녹화", lambda: self._begin("drive"), primary=True))
        layout.addWidget(button("주차 녹화", lambda: self._begin("parking")))
        layout.addStretch()
        self.pages.addWidget(self.confirmation)

    def _build_recording(self):
        self.recording_page, layout = page("DashPi")
        self.record_heading = self.recording_page.heading
        self.record_clock = QLabel(time.strftime("%H:%M", time.localtime()))
        self.record_clock.setObjectName("clock")
        layout.addWidget(self.record_clock)
        self.record_status = QLabel("카메라 준비 중")
        self.record_status.setObjectName("status")
        layout.addWidget(self.record_status)
        self.preview_host = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_host)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview = QLabel("카메라 연결 중")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_layout.addWidget(self.preview)
        layout.addWidget(self.preview_host, 1)
        controls = QHBoxLayout()
        self.analyze_button = button("사고 분석", self._trigger, primary=True)
        self.stop_button = button("종료", self._stop)
        controls.addWidget(self.analyze_button)
        controls.addWidget(self.stop_button)
        layout.addLayout(controls)
        self.pages.addWidget(self.recording_page)

    def recording_controls(self) -> list[QPushButton]:
        return [self.analyze_button, self.stop_button]

    def _build_records(self):
        self.records_page, layout = page("녹화기록", back=self.show_home)
        self.record_filter = QComboBox()
        self.record_filter.addItems(["전체", "주행", "사고", "주차"])
        self.record_filter.currentTextChanged.connect(self._refresh_records)
        layout.addWidget(self.record_filter)
        self.record_list = QListWidget()
        self.record_list.itemClicked.connect(self._open_record)
        layout.addWidget(self.record_list, 1)
        self.pages.addWidget(self.records_page)

    def _build_settings(self):
        self.settings_page, layout = page("설정", back=self.show_home)
        current = load_settings(self.settings_path)
        self.resolution = QComboBox()
        self.resolution.addItems(["1080p", "720p"])
        self.resolution.setCurrentText("1080p" if current.width == 1920 else "720p")
        self.fps = QComboBox()
        self.fps.addItems(["30 FPS", "24 FPS"])
        self.fps.setCurrentText(f"{current.fps} FPS")
        self.quality = QComboBox()
        self.quality.addItems(["4 Mbps", "8 Mbps", "12 Mbps"])
        self.quality.setCurrentText(f"{current.bitrate_mbps} Mbps")
        self.brightness = QDoubleSpinBox()
        self.brightness.setRange(-1, 1)
        self.brightness.setSingleStep(0.1)
        self.brightness.setValue(current.brightness)
        self.model = QLineEdit(current.ai_model)
        self.report_model = QLineEdit(current.ai_report_model)
        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for name, control in (("녹화 화질", self.resolution), ("프레임", self.fps),
                              ("비트레이트", self.quality), ("화면 밝기", self.brightness),
                              ("비전 모델", self.model), ("요약 모델", self.report_model)):
            label = QLabel(name)
            label.setMinimumHeight(52)
            form.addRow(label, control)
        self.ai_key_status = QLabel("")
        self.ai_key_status.setObjectName("caption")
        form.addRow(self.ai_key_status)
        self.storage_usage = QLabel("")
        self.storage_usage.setObjectName("caption")
        form.addRow(self.storage_usage)
        fields = QWidget()
        fields.setLayout(form)
        scroll = QScrollArea()
        scroll.setObjectName("plain")
        scroll.setWidgetResizable(True)
        scroll.setWidget(fields)
        QScroller.grabGesture(scroll.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        layout.addWidget(scroll, 1)
        self.settings_status = QLabel("")
        self.settings_status.setObjectName("caption")
        layout.addWidget(self.settings_status)
        actions = QHBoxLayout()
        self.exit_button = button("앱 종료", self._confirm_exit)
        self.exit_button.setObjectName("danger")
        actions.addWidget(self.exit_button)
        actions.addStretch()
        self.save_settings_button = button("저장", self._save_settings, primary=True)
        self.save_settings_button.setMinimumWidth(200)
        actions.addWidget(self.save_settings_button)
        layout.addLayout(actions)
        self.pages.addWidget(self.settings_page)

    def _build_detail(self):
        self.detail_page, layout = page("녹화 상세", back=self.show_records)
        self.detail_title = QLabel("")
        layout.addWidget(self.detail_title)
        self.player = QMediaPlayer(self)
        self.player.mediaStatusChanged.connect(self._advance_on_end)
        self.video = QVideoWidget()
        self.player.setVideoOutput(self.video)
        layout.addWidget(self.video, 1)
        self.segment_list = QListWidget()
        self.segment_list.itemClicked.connect(self._play_segment)
        layout.addWidget(self.segment_list)
        self.report_text = QLabel("")
        self.report_text.setWordWrap(True)
        report_scroll = QScrollArea()
        report_scroll.setWidgetResizable(True)
        report_scroll.setMaximumHeight(160)
        report_scroll.setWidget(self.report_text)
        layout.addWidget(report_scroll)
        # One row: stacked, these buttons made the page taller than the 480px LCD, and the window
        # grows to its tallest page, so every page (including the optical QR) spilled off-screen.
        actions = QHBoxLayout()
        actions.addWidget(button("재생 / 일시정지", self._toggle_playback))
        self.external_analyze_button = button("사고 분석", self._analyze_external, primary=True)
        self.external_analyze_button.hide()
        actions.addWidget(self.external_analyze_button)
        self.reanalyze_button = button("다시 분석", self._reanalyze, primary=True)
        self.reanalyze_button.hide()
        actions.addWidget(self.reanalyze_button)
        self.optical_button = button("리포트 QR 전송", self._open_selected_optical, primary=True)
        self.optical_button.hide()
        actions.addWidget(self.optical_button)
        self.delete_button = button("삭제", self._confirm_delete)
        self.delete_button.setObjectName("danger")
        actions.addWidget(self.delete_button)
        layout.addLayout(actions)
        self.pages.addWidget(self.detail_page)

    def _build_optical(self):
        self.optical_page, layout = page("광학 리포트 전송", back=self._leave_optical)
        self.optical_page.heading.hide()  # the QR needs the height; the title stays for the screen log
        warning = QLabel("이 QR은 호환 수신기로 누구나 촬영할 수 있습니다. 휴대폰 DashPi 수신 PWA를 여세요.")
        warning.setObjectName("caption")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.optical_status = QLabel("")
        self.optical_status.setObjectName("status")
        layout.addWidget(self.optical_status)
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # The pixmap must not size the label: otherwise one frame drawn before layout pins the
        # label (and the page) larger than the LCD, cutting off the QR and pushing 뒤로 off-screen.
        self.qr_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        layout.addWidget(self.qr_label, 1)
        self.pages.addWidget(self.optical_page)

    def show_home(self):
        self.pages.setCurrentWidget(self.home)

    def show_start_confirmation(self):
        self.pages.setCurrentWidget(self.confirmation)

    def show_recording(self):
        if self._preview_widget is not None:
            self.preview_layout.removeWidget(self._preview_widget)
            self._preview_widget.deleteLater()
        self.preview_layout.removeWidget(self.preview)
        self.preview.deleteLater()
        self.preview = self.session.recorder.create_preview(self.preview_host)
        self._preview_widget = self.preview
        self.preview_layout.addWidget(self.preview)
        self.record_status.setText("녹화 시작 중")
        self.pages.setCurrentWidget(self.recording_page)

    def show_records(self):
        self.optical_timer.stop()
        self._refresh_records()
        self.pages.setCurrentWidget(self.records_page)

    def show_settings(self):
        try:
            usage = shutil.disk_usage(self.settings_path.parent)
            self.storage_usage.setText(
                f"저장 공간: {usage.used / 2**30:.1f} GiB 사용 / {usage.total / 2**30:.1f} GiB 전체"
            )
        except OSError:
            self.storage_usage.setText("저장 공간을 확인할 수 없습니다.")
        self.ai_key_status.setText(
            "API 키: 설정됨" if api_key_configured() else "API 키: 없음 (~/.config/dashpi/ai.env)"
        )
        self.pages.setCurrentWidget(self.settings_page)

    def _begin(self, mode: str):
        if self._starting or self.session.recorder.recording:
            return
        self._starting = True
        self._recording_mode = mode
        self.record_status.setText("카메라 준비 중")
        self.analyze_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.pages.setCurrentWidget(self.recording_page)
        try:
            self.session.recorder.settings = load_settings(self.settings_path)
            if hasattr(self.session, "settings"):
                self.session.settings = replace(
                    self.session.settings,
                    ai_model=self.session.recorder.settings.ai_model,
                    ai_report_model=self.session.recorder.settings.ai_report_model,
                )
                self.session.analyze = build_analyzer(
                    self.session.settings.ai_model, self.session.settings.ai_report_model,
                    self.settings_path.parent,
                )
            self._submit(self.session.recorder.prepare, self._prepared)
        except Exception as error:
            log.exception("녹화 시작 실패")
            self._starting = False
            self.record_status.setText(str(error))
            self.stop_button.setEnabled(True)

    def _prepared(self, future: Future):
        if not self._report_error(future):
            self._starting = False
            self._release_camera()
            return
        try:
            self.show_recording()
        except Exception as error:
            log.exception("카메라 프리뷰 표시 실패")
            self.record_status.setText(str(error))
            self._starting = False
            self._release_camera()
            return
        self._submit(lambda: self.session.start(self._recording_mode), self._started)

    def _started(self, future: Future):
        self._starting = False
        if self._report_error(future):
            self._tracking_overlay_failed = False
            self._tracking_error_reported = None
            self.record_status.setText("녹화 중")
            self.analyze_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            if self._close_when_done:
                self._stop()
        else:
            self._release_camera()

    def _release_camera(self):
        self._clear_tracking_overlay()
        if self._preview_widget is not None:
            self.preview_layout.removeWidget(self._preview_widget)
            self._preview_widget.close()
            self._preview_widget.deleteLater()
            self._preview_widget = None
            self.preview = QLabel("카메라 연결 중")
            self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.preview_layout.addWidget(self.preview)
        self._submit(self.session.recorder.release, self._released)
        self.stop_button.setEnabled(True)

    def _released(self, future: Future):
        self._report_error(future)
        if self._close_when_done and not self.session.recorder.recording:
            self.close()

    def _trigger(self):
        if not self.analyze_button.isEnabled():
            return
        pressed_at = time.monotonic()
        self.record_status.setText("사고 이후 15초 수집 중")
        self._submit(lambda: self.session.trigger(pressed_at), self._report_error)

    def _stop(self):
        pressed_at = time.monotonic()
        self.record_status.setText("종료 요청 처리 중")
        self._submit(lambda: self.session.stop(pressed_at), self._stopped)

    def _stopped(self, future: Future):
        if not self.session.recorder.recording:
            self._clear_tracking_overlay()
        if not self._report_error(future):
            return
        if future.result():
            error = getattr(self.session, "last_error", None)
            if error:
                message = f"녹화 중단: {error}. 원본 영상은 보존됩니다."
                log.error(message)
                self.record_status.setText(message)
                self.home_status.setText(message)
                if self._close_when_done:
                    self.close()
                else:
                    self.show_home()
                return
            self.record_status.setText("녹화 종료")
            if self._close_when_done:
                self.close()
            else:
                self.show_home()
        else:
            self.record_status.setText("15초 수집 후 자동 종료됩니다.")

    def _submit(self, work, callback):
        self._jobs.append((self._executor.submit(work), callback))

    def _poll(self):
        recording = self.session.recorder.recording
        self.record_heading.setText("● REC" if recording else "DashPi")
        if self.record_heading.objectName() != ("rec" if recording else "title"):
            self.record_heading.setObjectName("rec" if recording else "title")
            self.record_heading.style().polish(self.record_heading)
        self.record_clock.setText(time.strftime("%H:%M", time.localtime()))
        for future, callback in list(self._jobs):
            if future.done():
                self._jobs.remove((future, callback))
                callback(future)
        if self._tick_future is not None and self._tick_future.done():
            tick_ok = self._report_error(self._tick_future)
            self._tick_future = None
            if not self.session.recorder.recording and self.session.pending_stop is False:
                error = getattr(self.session, "last_error", None)
                if error:
                    message = f"녹화 중단: {error}. 원본 영상은 보존됩니다."
                    log.error(message)
                    self.record_status.setText(message)
                    self.home_status.setText(message)
                elif not tick_ok:
                    pass
                elif self._close_when_done:
                    self.close()
                elif self.pages.currentWidget() is self.recording_page:
                    self.record_status.setText("녹화 종료")
                    self.show_home()
        if self.session.recorder.recording and self._tick_future is None:
            self._tick_future = self._executor.submit(lambda: self.session.tick(time.monotonic()))
        self._poll_tracking()

    def _tracking_failed(self, error):
        self._tracking_overlay_failed = True
        worker = getattr(self.session.recorder, "tracking_worker", None)
        if worker is not None:
            worker.stop_event.set()
        if str(error) != self._tracking_error_reported:
            self._tracking_error_reported = str(error)
            log.warning("추적 중단: %s", error)
            self.record_status.setText(self.record_status.text() + f" · 추적 중단: {error}")

    def _clear_tracking_overlay(self):
        try:
            # Closed cameras no longer display their overlay and reject even None.
            if (self._tracking_overlay_visible and self._preview_widget is not None
                    and self.session.recorder.picam2 is not None):
                self._preview_widget.set_overlay(None)
        except Exception as error:
            self._tracking_failed(error)
        finally:
            self._tracking_overlay_visible = False

    def _poll_tracking(self):
        recorder = self.session.recorder
        if not recorder.recording:
            self._clear_tracking_overlay()
            self._tracking_error_reported = None
            self._tracking_overlay_failed = False
            return
        if self._tracking_overlay_failed:
            return
        worker = getattr(recorder, "tracking_worker", None)
        result, error = worker.snapshot() if worker is not None else (None, None)
        error = error or getattr(recorder, "tracking_error", None)
        if error:
            self._tracking_failed(error)
            self._clear_tracking_overlay()
            return
        if result is None or time.monotonic() - result[0] > 1:
            self._clear_tracking_overlay()
            return
        if self._preview_widget is not None:
            try:
                from dashpi.live_tracking import render_overlay
                _, (height, width), tracks = result
                # Picamera2 scales the texture with the camera image, independent of widget size.
                self._preview_widget.set_overlay(render_overlay(width, height, tracks))
                self._tracking_overlay_visible = True
            except Exception as error:
                self._tracking_failed(error)
                self._clear_tracking_overlay()

    def _report_error(self, future: Future) -> bool:
        try:
            future.result()
            return True
        except Exception as error:
            log.error("작업 실패: %s", error, exc_info=error)
            self.record_status.setText(str(error))
            return False

    def _analyzer(self):
        current = load_settings(self.settings_path)
        return build_analyzer(current.ai_model, current.ai_report_model, self.settings_path.parent)

    def _start_retries(self):
        try:
            self.retrier.recover_interrupted()
        except Exception:
            log.exception("중단된 분석 복구 실패")
        self._retry_tick()

    def _retry_tick(self):
        if self.retrier is None:
            return
        try:
            self.retrier.tick()
        except Exception:
            log.exception("분석 재시도 확인 실패")

    def _run_retry(self, incident_id: str):
        current = load_settings(self.settings_path)
        settings = replace(self.session.settings, ai_model=current.ai_model,
                           ai_report_model=current.ai_report_model)
        pipeline = IncidentPipeline(settings, self.store, getattr(self.session, "detector", None),
                                    wait_for_capacity=self.session.worker.wait_for_capacity)

        def run():
            manual = self.store.load(incident_id).manual_offset_seconds
            return pipeline.regenerate_report(incident_id, self._analyzer(), manual)
        return self.session.worker.submit(run)

    def _reanalyze(self):
        incident = self._selected_incident
        if incident is None:
            return
        try:
            item = self.store.load(incident.incident_id)
        except (FileNotFoundError, KeyError, OSError, TypeError, ValueError):
            self.reanalyze_button.hide()
            self.report_text.setText("사고 기록을 찾을 수 없습니다.")
            return
        if item.state is not IncidentState.ANALYSIS_FAILED:
            return
        now = datetime.now(UTC).isoformat()
        item.analysis_attempts, item.next_analysis_at = 0, now
        item.transition(IncidentState.AWAITING_ANALYSIS, now, "다시 분석 요청")
        self.store.save(item)
        self._selected_incident = item
        self.reanalyze_button.hide()
        self.report_text.setText("분석 대기 · 곧 다시 분석합니다.")
        self._retry_tick()

    def _save_settings(self):
        try:
            width, height = (1920, 1080) if self.resolution.currentText() == "1080p" else (1280, 720)
            settings = VideoSettings(
                width=width, height=height, fps=int(self.fps.currentText().split()[0]),
                bitrate_mbps=int(self.quality.currentText().split()[0]),
                brightness=self.brightness.value(), ai_model=self.model.text().strip(),
                ai_report_model=self.report_model.text().strip(),
            )
            save_settings(self.settings_path, settings)
            self.settings_status.setText("저장했습니다. 다음 녹화부터 적용됩니다.")
        except Exception as error:
            log.exception("설정 저장 실패")
            self.settings_status.setText(str(error))

    def _confirm(self, title: str, text: str, action: str) -> bool:
        box = QMessageBox(
            QMessageBox.Icon.Question, title, text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self,
        )
        confirm, cancel = box.button(QMessageBox.StandardButton.Yes), box.button(QMessageBox.StandardButton.No)
        confirm.setText(action)
        confirm.setObjectName("danger")
        confirm.style().polish(confirm)  # the dialog already styled its buttons before the rename
        cancel.setText("취소")
        box.setDefaultButton(cancel)  # Enter or a stray tap on the default must not destroy anything
        box.exec()
        return box.clickedButton() is confirm

    def _confirm_exit(self):
        if self._confirm("DashPi 종료", "앱을 종료하시겠습니까?", "종료"):
            self.close()

    def _confirm_delete(self):
        kind, value = self._selected_record
        if kind == "incident":
            what = "이 사고 기록(사고 영상과 분석 리포트)을"
        elif kind == "recording":
            what = f"이 녹화 영상(조각 {len(value.segments)}개)을"
        else:
            what = f"동영상 폴더의 원본 파일 {value.name}을(를)"
        if not self._confirm("기록 삭제", f"{what} 삭제합니다.\n삭제하면 되돌릴 수 없습니다.", "삭제"):
            return
        self._detail_generation += 1
        self.player.stop()
        self.player.setSource(QUrl())  # release the file before it goes away
        try:
            if kind == "incident":
                self.store.delete(value.incident_id)
            elif kind == "recording":
                self.session.delete_recording(value.segments[0].path.parent)
            else:
                value.unlink()
        except Exception as error:
            log.exception("기록 삭제 실패")
            self.report_text.setText(f"삭제하지 못했습니다: {error}")
            return
        log.info("기록 삭제: %s", self.detail_title.text())
        self.show_records()

    def _refresh_records(self):
        self.record_list.clear()
        filter_name = self.record_filter.currentText()
        if filter_name == "전체":
            for source in sorted((Path.home() / "Videos").glob("*.mp4")):
                if source.is_file():
                    item = QListWidgetItem(f"외부 영상 · {source.name}")
                    item.setData(Qt.ItemDataRole.UserRole, ("external", source))
                    self.record_list.addItem(item)
        if filter_name in {"전체", "사고"}:
            for incident in self.store.list():
                label = f"사고 · {local_time(incident.triggered_at)} · {STATE_LABELS[incident.state]}"
                if incident.failure_reason and incident.state in (
                        IncidentState.AWAITING_ANALYSIS, IncidentState.ANALYSIS_FAILED):
                    label += f" ({incident.failure_reason})"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, ("incident", incident))
                self.record_list.addItem(item)
        if filter_name in {"전체", "주행", "주차"}:
            for recording in self.session.recorder.list_recordings():
                if filter_name == "주행" and recording.mode != "drive":
                    continue
                if filter_name == "주차" and recording.mode != "parking":
                    continue
                label = "주행" if recording.mode == "drive" else "주차"
                item = QListWidgetItem(f"{label} · {local_time(recording.started_at)}")
                item.setData(Qt.ItemDataRole.UserRole, ("recording", recording))
                self.record_list.addItem(item)

    def _open_record(self, item: QListWidgetItem):
        self._detail_generation += 1
        generation = self._detail_generation
        self.player.stop()
        self.player.setSource(QUrl())
        kind, value = item.data(Qt.ItemDataRole.UserRole)
        self._selected_record = (kind, value)
        self.delete_button.setEnabled(True)
        self._selected_incident = value if kind == "incident" else None
        self._selected_external = value if kind == "external" else None
        self.external_analyze_button.setVisible(kind == "external")
        self.external_analyze_button.setEnabled(True)
        self.optical_button.setVisible(
            kind == "incident" and value.state is IncidentState.READY
            and value.report_html is not None
        )
        self.reanalyze_button.setVisible(kind == "incident" and value.state is IncidentState.ANALYSIS_FAILED)
        self.segment_list.clear()
        self.report_text.setText("")
        self.detail_title.setText(item.text())
        if kind == "external":
            part = QListWidgetItem(value.name)
            part.setData(Qt.ItemDataRole.UserRole, value)
            self.segment_list.addItem(part)
        elif kind == "recording":
            for segment in value.segments:
                part = QListWidgetItem(segment.path.name)
                part.setData(Qt.ItemDataRole.UserRole, segment.path)
                self.segment_list.addItem(part)
        else:
            if value.clip is not None:
                self._submit(
                    lambda: self._verified_clip_path(value),
                    lambda future: self._clip_checked(future, generation),
                )
            if value.state is IncidentState.AWAITING_ANALYSIS:
                when = ""
                if value.next_analysis_at:
                    when = f" · 다음 시도 {datetime.fromisoformat(value.next_analysis_at).astimezone():%H:%M}"
                self.report_text.setText(f"분석 대기 · {value.failure_reason or ''}{when}")
            elif value.state is IncidentState.ANALYSIS_FAILED:
                self.report_text.setText(
                    f"AI 분석에 실패했습니다: {value.failure_reason or '알 수 없음'}. 원본 사고 영상은 보존됩니다."
                )
            elif value.report_json is not None:
                try:
                    with self.store.open_incident(value.incident_id) as (_item, descriptor, directory):
                        if value.report_json.path != directory / "report.json":
                            raise ValueError("invalid report path")
                        source, _ = _open_verified_file(
                            descriptor, "report.json", value.report_json.byte_length,
                            value.report_json.sha256,
                        )
                        with source:
                            source.seek(0)
                            report = json.loads(source.read())
                    if not isinstance(report, dict):
                        raise ValueError("invalid report")
                    lines = [str(report.get("summary", ""))]
                    for observation in report.get("observations", []):
                        lines.append(
                            f"{float(observation['timestamp']):.1f}초 · {observation['description']}"
                        )
                    for limitation in report.get("limitations", []):
                        lines.append(f"한계: {limitation}")
                    for warning in report.get("warnings", []):
                        lines.append(f"주의: {warning}")
                    self.report_text.setText("\n".join(lines))
                except Exception:
                    log.exception("리포트 검증 실패")
                    self.report_text.setText("리포트를 검증할 수 없습니다.")
        if self.segment_list.count():
            self._play_segment(self.segment_list.item(0))
        self.pages.setCurrentWidget(self.detail_page)

    def _build_analysis(self):
        self.analysis_page, layout = page("AI 사고 분석", back=lambda: self.pages.setCurrentWidget(self.detail_page))
        layout.setSpacing(8)
        self.analysis_subtitle = QLabel("")
        self.analysis_subtitle.setObjectName("caption")
        layout.addWidget(self.analysis_subtitle)
        self._step_rows = {}
        for step, text in ANALYSIS_STEPS:
            row = QWidget()
            row.setFixedHeight(29)
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(10)
            icon, detail, clock = StepIcon(), QLabel(""), QLabel("")
            detail.setObjectName("caption")
            clock.setObjectName("caption")
            clock.setFixedWidth(56)
            clock.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            line.addWidget(icon)
            line.addWidget(QLabel(text))
            line.addStretch()
            line.addWidget(detail)
            line.addWidget(clock)
            layout.addWidget(row)
            self._step_rows[step] = {"icon": icon, "detail": detail, "clock": clock, "since": None, "took": None}
        self.analysis_stream = QLabel("")
        self.analysis_stream.setObjectName("caption")
        self.analysis_stream.setWordWrap(True)
        self.analysis_stream.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.analysis_stream.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        layout.addWidget(self.analysis_stream, 1)
        self.analysis_elapsed = QLabel("")
        self.analysis_elapsed.setObjectName("status")
        layout.addWidget(self.analysis_elapsed)
        self._analysis_events: deque = deque()
        self._analysis_started = time.monotonic()
        self._stream_done, self._stream_queue, self._stream_typing, self._stream_ask = [], [], None, None
        self.analysis_timer = QTimer(self)
        self.analysis_timer.timeout.connect(self._tick_analysis)
        self.pages.addWidget(self.analysis_page)

    def _start_analysis_view(self, subtitle: str):
        self._analysis_events = deque()
        self._analysis_started = time.monotonic()
        self._stream_done, self._stream_queue, self._stream_typing, self._stream_ask = [], [], None, None
        for row in self._step_rows.values():
            row["icon"].state = "pending"
            row["icon"].update()
            row["detail"].setText("")
            row["clock"].setText("")
            row["since"] = row["took"] = None
        self.analysis_subtitle.setText(subtitle)
        self.analysis_elapsed.setText("")
        self.analysis_stream.setText("")
        self.pages.setCurrentWidget(self.analysis_page)
        self.analysis_timer.start(80)

    def _tick_analysis(self):
        now = time.monotonic()
        while self._analysis_events:
            self._apply_step(now, *self._analysis_events.popleft())
        for row in self._step_rows.values():
            if row["since"] is not None and row["took"] is None:
                row["clock"].setText(f"{now - row['since']:.0f}초")
                row["icon"].angle = (row["icon"].angle + 24) % 360
                row["icon"].update()
        self.analysis_elapsed.setText(f"경과 {now - self._analysis_started:.0f}초")
        # Type the model's real output out a few characters at a time instead of a static "분석 중".
        if self._stream_typing is None and self._stream_queue:
            self._stream_typing = [self._stream_queue.pop(0), 0]
        if self._stream_typing is not None:
            self._stream_typing[1] += 3
            if self._stream_typing[1] >= len(self._stream_typing[0]):
                self._stream_done.append(self._stream_typing[0])
                self._stream_typing = None
        self._render_stream()

    def _apply_step(self, now: float, step: str, state: str, detail: str, payload) -> None:
        row = self._step_rows.get(step)
        if row is None:
            return
        row["icon"].state = state
        row["icon"].update()
        if state == "start":
            row["since"] = now
            row["detail"].setText(f"{detail} 호출 중" if detail else "진행 중")
            self._stream_ask = AI_ASKS.get(step)
            return
        if self._stream_ask == AI_ASKS.get(step):
            self._stream_ask = None
        row["took"] = now - row["since"] if row["since"] is not None else 0.0
        row["clock"].setText(f"{row['took']:.1f}초" if state == "done" else "")
        row["detail"].setText(detail)
        if step == "observe" and state == "done":
            for item in payload or []:
                self._stream_queue.append(f"{float(item['timestamp']):.1f}초 · {item['description']}")

    def _render_stream(self):
        # One pinned line for what the AI is being asked now, then the one observation being typed:
        # a long observation wraps to two lines, and three lines is all the 480px LCD has room for.
        lines = [f"→ {self._stream_ask}"] if self._stream_ask else []
        if self._stream_typing is not None:
            text, shown = self._stream_typing
            lines.append(text[:shown] + "▍")
        else:
            lines += self._stream_done[-1:]
        self.analysis_stream.setText("\n".join(lines))

    def _stop_analysis_view(self, failed: bool, message: str):
        self._tick_analysis()
        self.analysis_timer.stop()
        for row in self._step_rows.values():
            if row["since"] is not None and row["took"] is None:
                row["icon"].state = "fail" if failed else "skip"
                row["icon"].update()
                row["clock"].setText("")
        self._stream_done, self._stream_queue, self._stream_typing, self._stream_ask = [message], [], None, None
        self._render_stream()
        self.analysis_elapsed.setText("")

    def _analyze_external(self):
        source = self._selected_external
        if source is None or not self.external_analyze_button.isEnabled():
            return
        position = self.player.position() / 1000.0
        generation = self._detail_generation
        self.external_analyze_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.report_text.setText("사고 영상 분석 중...")
        self._start_analysis_view(f"{source.name} · 멈춘 위치 {position:.1f}초")
        events = self._analysis_events
        try:
            current = load_settings(self.settings_path)
            settings = replace(self.session.settings, ai_model=current.ai_model,
                               ai_report_model=current.ai_report_model)
            analyze = build_analyzer(settings.ai_model, settings.ai_report_model, self.settings_path.parent)
            def run():
                with progress.reporting(lambda *event: events.append(event)):
                    return analyze_external_video(source, position, settings, self.store, analyze)

            future = self.session.worker.submit(run)
            self._jobs.append((future, lambda done: self._external_analysis_done(done, generation)))
        except Exception as error:
            log.exception("외부 영상 분석 시작 실패")
            self.external_analyze_button.setEnabled(True)
            self.delete_button.setEnabled(True)
            self.report_text.setText(f"분석을 시작할 수 없습니다: {error}")
            self._stop_analysis_view(True, f"분석을 시작할 수 없습니다: {error}")

    def _external_analysis_done(self, future: Future, generation: int):
        if generation != self._detail_generation:
            return
        self.external_analyze_button.setEnabled(True)
        self.delete_button.setEnabled(True)
        try:
            incident = future.result()
        except Exception as error:
            log.error("외부 영상 분석 실패", exc_info=error)
            message = f"분석 실패: {error}. 원본 영상은 보존됩니다."
            self.report_text.setText(message)
            self._stop_analysis_view(True, message)
            return
        if incident.state is IncidentState.AWAITING_ANALYSIS:
            message = f"분석 대기 · {incident.failure_reason} · 연결되면 자동으로 분석합니다."
            self.report_text.setText(message)
            self._stop_analysis_view(False, message)
            return
        if incident.state is not IncidentState.READY:
            log.warning("외부 영상 분석 결과: %s (%s)", incident.state.value, incident.failure_reason)
            message = f"분석 실패: {incident.failure_reason or incident.state.value}. 원본 영상은 보존됩니다."
            self.report_text.setText(message)
            self._stop_analysis_view(True, message)
            return
        self._selected_incident = incident
        self.report_text.setText("분석 완료. 광학 리포트를 표시합니다.")
        self.optical_button.show()
        self._stop_analysis_view(False, "분석 완료 · 잠시 후 QR 전송 화면으로 넘어갑니다.")
        if self.pages.currentWidget() is self.analysis_page:
            # Let the finished checklist register before the QR screen replaces it.
            QTimer.singleShot(1500, lambda: self._open_finished_report(incident, generation))

    def _open_finished_report(self, incident, generation: int):
        if generation == self._detail_generation and self.pages.currentWidget() is self.analysis_page:
            self.start_optical(incident)

    def _verified_clip_path(self, incident):
        with self.store.open_incident(incident.incident_id) as (_item, descriptor, directory):
            if incident.clip.path != directory / "clip.mp4":
                raise ValueError("invalid clip path")
            source, _ = _open_verified_file(
                descriptor, "clip.mp4", incident.clip.byte_length, incident.clip.sha256
            )
            source.close()
        return incident.clip.path

    def _clip_checked(self, future: Future, generation: int):
        if generation != self._detail_generation:
            return
        try:
            path = future.result()
        except Exception as error:
            log.error("사고 영상 검증 실패", exc_info=error)
            self.report_text.setText(
                "\n".join(filter(None, [self.report_text.text(), "사고 영상을 검증할 수 없습니다."]))
            )
            return
        part = QListWidgetItem("사고 증거 영상")
        part.setData(Qt.ItemDataRole.UserRole, path)
        self.segment_list.addItem(part)
        if self.pages.currentWidget() is self.detail_page:
            self._play_segment(part)

    def _open_selected_optical(self):
        if self._selected_incident is not None:
            self.start_optical(self._selected_incident)

    def start_optical(self, incident):
        self._optical_generation += 1
        generation = self._optical_generation
        self.optical_timer.stop()
        self.optical_session = None
        self.qr_label.clear()
        self.pages.setCurrentWidget(self.optical_page)
        self.optical_status.setText("리포트 준비 중...")
        self._submit(
            lambda: self._prepare_optical(incident),
            lambda future: self._optical_ready(future, generation),
        )

    def _prepare_optical(self, incident):
        with self.store.open_incident(incident.incident_id) as (current, descriptor, directory):
            artifact = current.report_html
            if current.state is not IncidentState.READY or artifact is None:
                raise ValueError("리포트가 준비되지 않았습니다.")
            if artifact.byte_length > MAX_PAYLOAD:
                return None
            if artifact.path != directory / "report.html":
                raise ValueError("invalid report path")
            source, _ = _open_verified_file(
                descriptor, "report.html", artifact.byte_length, artifact.sha256
            )
            with source:
                source.seek(0)
                payload = source.read()
        return OpticalSession.from_bytes(
            "report.html", payload, "text/html", 512, secrets.randbits(32)
        )

    def _optical_ready(self, future: Future, generation: int):
        if generation != self._optical_generation or self.pages.currentWidget() is not self.optical_page:
            return
        try:
            self.optical_session = future.result()
        except Exception as error:
            log.error("QR 전송 준비 실패", exc_info=error)
            self.optical_status.setText("리포트를 검증하거나 QR 전송을 시작할 수 없습니다.")
            return
        if self.optical_session is None:
            self.optical_status.setText("16 MiB를 초과해 QR 전송을 사용할 수 없습니다. 로컬 리포트는 보존됩니다.")
            return
        self._optical_sequence = 0
        self.optical_status.setText("휴대폰 수신 PWA로 QR 프레임을 계속 비추세요.")
        self._render_optical_frame()
        self.optical_timer.start(250)

    def _render_optical_frame(self):
        if self.optical_session is None:
            return
        import qrcode

        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, border=4)
        qr.add_data(self.optical_session.frame(self._optical_sequence))
        try:
            qr.make(fit=True)
        except ValueError:
            # A malformed QR encoding must not halt the fountain stream; the receiver tolerates loss.
            self._optical_sequence = (self._optical_sequence + 1) % (2**32)
            return
        matrix = qr.get_matrix()
        width = len(matrix)
        image = QImage(width, width, QImage.Format.Format_RGB32)
        image.fill(0xFFFFFFFF)
        for y, row in enumerate(matrix):
            for x, dark in enumerate(row):
                if dark:
                    image.setPixel(x, y, 0xFF000000)
        size = max(1, min(self.qr_label.width(), self.qr_label.height(), 480))
        self.qr_label.setPixmap(
            QPixmap.fromImage(image).scaled(
                size, size, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        )
        self._optical_sequence = (self._optical_sequence + 1) % (2**32)

    def _leave_optical(self):
        self._optical_generation += 1
        self.optical_timer.stop()
        self.pages.setCurrentWidget(self.detail_page)
        if self.player.source().isEmpty() and self.segment_list.count():
            self._play_segment(self.segment_list.item(0))

    def _play_segment(self, item: QListWidgetItem):
        self.segment_list.setCurrentItem(item)
        self.player.setSource(QUrl.fromLocalFile(str(item.data(Qt.ItemDataRole.UserRole))))
        self.player.play()

    def _advance_on_end(self, status):
        if status is not QMediaPlayer.MediaStatus.EndOfMedia:
            return
        if self.pages.currentWidget() is not self.detail_page:
            return
        index = self.segment_list.currentRow() + 1
        if index < self.segment_list.count():
            self._play_segment(self.segment_list.item(index))

    def _toggle_playback(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def closeEvent(self, event):
        if self._starting:
            self._close_when_done = True
            event.ignore()
            return
        if self.session.recorder.recording:
            if not self._close_when_done:
                self._close_when_done = True
                self._stop()
            event.ignore()
            return
        self.timer.stop()
        if self.retrier is not None:
            self.retry_timer.stop()
        self.optical_timer.stop()
        self.player.stop()
        self._executor.shutdown(wait=False, cancel_futures=False)
        event.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path.home() / ".local/share/dashpi")
    parser.add_argument("--tracking-model", type=Path)
    parser.add_argument("--tracking-fps", type=float, default=10)
    parser.add_argument("--tracking-confidence", type=float, default=.10)
    parser.add_argument("--tracking-activation", type=float, default=.45)
    args = parser.parse_args()
    if (not all(math.isfinite(value) for value in
                (args.tracking_fps, args.tracking_confidence, args.tracking_activation))
            or not 0 < args.tracking_fps <= 10 or not 0 <= args.tracking_confidence < 1
            or not 0 < args.tracking_activation < 1):
        parser.error("invalid tracking thresholds or FPS")
    root = args.data_root
    setup_logging(root)
    # 원격 접속처럼 느린 화면에서 아이콘을 여러 번 누르면 전체화면 창이 겹쳐 떠서
    # 종료해도 아래 창이 남아 보이고, 분석 재시도도 서로 충돌한다.
    lock = QLockFile(str(root / "dashpi.lock"))
    if not lock.tryLock(0):
        log.info("DashPi 이미 실행 중 — 새 실행을 건너뜀")
        return
    log.info("DashPi 시작 (data root: %s)", root)
    current = load_settings(root / "settings.json")
    app = QApplication([])
    worker = AnalysisWorker()
    recorder = PiCameraRecorder(root, current, tracking_model=args.tracking_model,
                                tracking_fps=args.tracking_fps,
                                tracking_confidence=args.tracking_confidence,
                                tracking_activation=args.tracking_activation)
    settings = Settings(root, current.ai_model, current.ai_report_model)
    session = DeviceSession(recorder, settings, IncidentStore(root), worker,
                            build_analyzer(settings.ai_model, settings.ai_report_model, root))
    window = DashPiWindow(session, IncidentStore(root), root / "settings.json")
    try:
        app.exec()
    finally:
        log.info("DashPi 종료")
        worker.close()


if __name__ == "__main__":
    main()
