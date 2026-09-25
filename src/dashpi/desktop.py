"""Native Qt Widgets controls for the Raspberry Pi display."""

from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
import faulthandler
import json
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import secrets
import shutil
import sys
import threading
import time

from PySide6.QtCore import Qt, QtMsgType, QRect, QTimer, QUrl, QSize, qInstallMessageHandler
from PySide6.QtGui import QIcon, QImage, QPixmap
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


def page(title: str) -> tuple[QWidget, QVBoxLayout]:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(24, 20, 24, 20)
    layout.setSpacing(14)
    heading = QLabel(title)
    heading.setObjectName("title")
    layout.addWidget(heading)
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
        self.optical_session: OpticalSession | None = None
        self._optical_sequence = 0
        self._optical_generation = 0
        self._selected_incident = None
        self._selected_external: Path | None = None
        self._detail_generation = 0
        self.pages = QStackedWidget()
        self.pages.currentChanged.connect(
            lambda index: log.info("화면: %s", self.pages.widget(index).layout().itemAt(0).widget().text())
        )
        self.setCentralWidget(self.pages)

        self._build_home()
        self._build_confirmation()
        self._build_recording()
        self._build_records()
        self._build_settings()
        self._build_detail()
        self._build_optical()
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
        self.confirmation, layout = page("녹화 시작")
        description = QLabel("카메라로 영상을 기록합니다. 주행 또는 수동 주차 녹화를 선택하세요.")
        description.setObjectName("caption")
        layout.addWidget(description)
        layout.addWidget(button("주행 녹화", lambda: self._begin("drive"), primary=True))
        layout.addWidget(button("주차 녹화", lambda: self._begin("parking")))
        layout.addStretch()
        layout.addWidget(button("뒤로", self.show_home))
        self.pages.addWidget(self.confirmation)

    def _build_recording(self):
        self.recording_page, layout = page("DashPi")
        self.record_heading = layout.itemAt(0).widget()
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
        self.records_page, layout = page("녹화기록")
        self.record_filter = QComboBox()
        self.record_filter.addItems(["전체", "주행", "사고", "주차"])
        self.record_filter.currentTextChanged.connect(self._refresh_records)
        layout.addWidget(self.record_filter)
        self.record_list = QListWidget()
        self.record_list.itemClicked.connect(self._open_record)
        layout.addWidget(self.record_list, 1)
        layout.addWidget(button("뒤로", self.show_home))
        self.pages.addWidget(self.records_page)

    def _build_settings(self):
        self.settings_page, layout = page("설정")
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
        actions.addWidget(button("뒤로", self.show_home))
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
        self.detail_page, layout = page("녹화 상세")
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
        self.external_analyze_button = button("사고 분석", self._analyze_external, primary=True)
        self.external_analyze_button.hide()
        layout.addWidget(self.external_analyze_button)
        self.reanalyze_button = button("다시 분석", self._reanalyze, primary=True)
        self.reanalyze_button.hide()
        layout.addWidget(self.reanalyze_button)
        self.optical_button = button("리포트 QR 전송", self._open_selected_optical, primary=True)
        self.optical_button.hide()
        layout.addWidget(self.optical_button)
        layout.addWidget(button("재생 / 일시정지", self._toggle_playback))
        layout.addWidget(button("뒤로", self.show_records))
        self.pages.addWidget(self.detail_page)

    def _build_optical(self):
        self.optical_page, layout = page("광학 리포트 전송")
        warning = QLabel("이 QR은 호환 수신기로 누구나 촬영할 수 있습니다. 휴대폰 DashPi 수신 PWA를 여세요.")
        warning.setObjectName("caption")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.optical_status = QLabel("")
        self.optical_status.setObjectName("status")
        layout.addWidget(self.optical_status)
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.qr_label, 1)
        layout.addWidget(button("뒤로", self._leave_optical))
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
            self.record_status.setText("녹화 중")
            self.analyze_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            if self._close_when_done:
                self._stop()
        else:
            self._release_camera()

    def _release_camera(self):
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

    def _confirm_exit(self):
        box = QMessageBox(
            QMessageBox.Icon.Question, "DashPi 종료", "앱을 종료하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self,
        )
        confirm, cancel = box.button(QMessageBox.StandardButton.Yes), box.button(QMessageBox.StandardButton.No)
        confirm.setText("종료")
        confirm.setObjectName("danger")
        confirm.style().polish(confirm)  # the dialog already styled its buttons before the rename
        cancel.setText("취소")
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() is confirm:
            self.close()

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

    def _analyze_external(self):
        source = self._selected_external
        if source is None or not self.external_analyze_button.isEnabled():
            return
        position = self.player.position() / 1000.0
        generation = self._detail_generation
        self.external_analyze_button.setEnabled(False)
        self.report_text.setText("사고 영상 분석 중...")
        try:
            current = load_settings(self.settings_path)
            settings = replace(self.session.settings, ai_model=current.ai_model,
                               ai_report_model=current.ai_report_model)
            analyze = build_analyzer(settings.ai_model, settings.ai_report_model, self.settings_path.parent)
            future = self.session.worker.submit(
                lambda: analyze_external_video(source, position, settings, self.store, analyze)
            )
            self._jobs.append((future, lambda done: self._external_analysis_done(done, generation)))
        except Exception as error:
            log.exception("외부 영상 분석 시작 실패")
            self.external_analyze_button.setEnabled(True)
            self.report_text.setText(f"분석을 시작할 수 없습니다: {error}")

    def _external_analysis_done(self, future: Future, generation: int):
        if generation != self._detail_generation or self.pages.currentWidget() is not self.detail_page:
            return
        self.external_analyze_button.setEnabled(True)
        try:
            incident = future.result()
        except Exception as error:
            log.error("외부 영상 분석 실패", exc_info=error)
            self.report_text.setText(f"분석 실패: {error}. 원본 영상은 보존됩니다.")
            return
        if incident.state is IncidentState.AWAITING_ANALYSIS:
            self.report_text.setText(f"분석 대기 · {incident.failure_reason} · 연결되면 자동으로 분석합니다.")
            return
        if incident.state is not IncidentState.READY:
            log.warning("외부 영상 분석 결과: %s (%s)", incident.state.value, incident.failure_reason)
            self.report_text.setText(
                f"분석 실패: {incident.failure_reason or incident.state.value}. 원본 영상은 보존됩니다."
            )
            return
        self._selected_incident = incident
        self.report_text.setText("분석 완료. 광학 리포트를 표시합니다.")
        self.optical_button.show()
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
        size = max(180, min(self.qr_label.width(), self.qr_label.height(), 480))
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
    args = parser.parse_args()
    root = args.data_root
    setup_logging(root)
    log.info("DashPi 시작 (data root: %s)", root)
    current = load_settings(root / "settings.json")
    app = QApplication([])
    worker = AnalysisWorker()
    recorder = PiCameraRecorder(root, current)
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
