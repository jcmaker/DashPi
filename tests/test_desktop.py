import time
from threading import Event
from types import SimpleNamespace
from datetime import UTC, datetime
import json

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QToolButton
from PySide6.QtMultimedia import QMediaPlayer

from dashpi.device import Recording, VideoSettings, load_settings
from dashpi.models import IncidentMetadata, IncidentState, Segment
from dashpi.optical.container import unpack_container
from dashpi.optical.fountain import FountainDecoder
from dashpi.optical.protocol import parse_frame
from dashpi.optical.session import OpticalSession
from dashpi.storage import IncidentStore, atomic_write


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class FakeRecorder:
    def __init__(self):
        self.recording = False
        self.picam2 = object()
        self.prepared = False
        self.prepare_count = 0

    def prepare(self):
        self.prepared = True
        self.prepare_count += 1
        self.picam2 = object()

    def release(self):
        self.prepared = False
        self.picam2 = None

    def create_preview(self, parent=None):
        return QLabel("live camera", parent)

    def list_recordings(self):
        return getattr(self, "recordings", [])


class FakeSession:
    def __init__(self):
        self.recorder = FakeRecorder()
        self.pending_stop = False
        self.start_count = 0
        self.stop_count = 0

    def start(self, mode):
        self.start_count += 1
        self.mode = mode
        self.recorder.recording = True

    def trigger(self, now):
        self.trigger_at = now
        self.pending_stop = True

    def stop(self, now):
        self.stop_count += 1
        if self.pending_stop:
            return False
        self.recorder.recording = False
        return True

    def tick(self, now):
        pass


def wait_until(qapp, predicate, seconds=2):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("UI did not reach expected state")


def test_home_and_recording_controls_are_native_and_exact(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    session = FakeSession()
    window = DashPiWindow(session, IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        tiles = window.home.findChildren(QToolButton)
        assert {button.text() for button in tiles} == {
            "녹화기록", "주행시작", "설정"
        }
        assert all(button.minimumHeight() >= 140 for button in tiles)
        window.show_recording()
        assert [button.text() for button in window.recording_controls()] == ["사고 분석", "종료"]
        assert window.preview.text() == "live camera"
        assert not any("음성" in label.text() or "GPS" in label.text()
                       for label in window.findChildren(QLabel))
    finally:
        window.close()


def test_native_window_opens_full_screen(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    window = DashPiWindow(FakeSession(), IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        wait_until(qapp, window.isFullScreen)
        assert window.isVisible()
        assert window.isFullScreen()
    finally:
        window.close()


def test_external_video_appears_in_records_and_opens_for_playback(qapp, tmp_path, monkeypatch):
    import dashpi.desktop as desktop

    videos = tmp_path / "Videos"
    videos.mkdir()
    source = videos / "CQkN1776752331_423_com.mp4"
    source.write_bytes(b"test video")
    monkeypatch.setattr(desktop.Path, "home", lambda: tmp_path)
    window = desktop.DashPiWindow(FakeSession(), IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        window.show_records()
        items = [window.record_list.item(index) for index in range(window.record_list.count())]
        video_item = next(item for item in items if source.name in item.text())
        window._open_record(video_item)
        assert window.player.source().toLocalFile() == str(source)
    finally:
        window.close()


def test_external_video_analysis_opens_optical_report(qapp, tmp_path, monkeypatch):
    import dashpi.desktop as desktop
    from dashpi.analysis_worker import AnalysisWorker
    from dashpi.config import Settings

    source = tmp_path / "Videos" / "source.mp4"
    source.parent.mkdir()
    source.write_bytes(b"video")
    monkeypatch.setattr(desktop.Path, "home", lambda: tmp_path)
    store = IncidentStore(tmp_path / "data")
    incident = IncidentMetadata.new("external-result", datetime.now(UTC).isoformat(), 0, 1)
    incident.transition(IncidentState.READY, datetime.now(UTC).isoformat())
    incident.report_html = atomic_write(store.directory(incident.incident_id) / "report.html", b"report")
    store.save(incident)
    monkeypatch.setattr(desktop, "analyze_external_video", lambda *_args: incident, raising=False)
    session = FakeSession()
    session.worker = AnalysisWorker()
    session.settings = Settings(store.root, "test-model")
    session.analyze = lambda _frames: {}
    window = desktop.DashPiWindow(session, store, store.root / "settings.json")
    try:
        window.show_records()
        window._open_record(window.record_list.item(0))
        window.external_analyze_button.click()
        wait_until(qapp, lambda: window.pages.currentWidget() is window.optical_page)
    finally:
        window.close()
        session.worker.close()


def test_settings_save_supported_camera_options(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    path = tmp_path / "settings.json"
    window = DashPiWindow(FakeSession(), IncidentStore(tmp_path), path)
    try:
        window.show_settings()
        window.resolution.setCurrentText("720p")
        window.fps.setCurrentText("24 FPS")
        window.save_settings_button.click()
        assert load_settings(path) == VideoSettings(width=1280, height=720, fps=24)
    finally:
        window.close()


def test_settings_show_disk_usage(qapp, tmp_path, monkeypatch):
    import dashpi.desktop as desktop

    monkeypatch.setattr(
        desktop.shutil, "disk_usage",
        lambda path: SimpleNamespace(total=20 * 2**30, used=5 * 2**30, free=15 * 2**30),
    )
    window = desktop.DashPiWindow(FakeSession(), IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        window.show_settings()
        assert "5.0 GiB" in window.storage_usage.text()
        assert "20.0 GiB" in window.storage_usage.text()
    finally:
        window.close()


def test_settings_exit_requires_confirmation(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    window = DashPiWindow(FakeSession(), IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        window.show_settings()

        def answer(choice):
            dialog = QApplication.activeModalWidget()
            assert isinstance(dialog, QMessageBox)
            dialog.button(choice).click()

        QTimer.singleShot(0, lambda: answer(QMessageBox.StandardButton.No))
        window.exit_button.click()
        assert window.isVisible()
        assert window.pages.currentWidget() is window.settings_page

        QTimer.singleShot(0, lambda: answer(QMessageBox.StandardButton.Yes))
        window.exit_button.click()
        assert not window.isVisible()
    finally:
        window.close()


def test_recording_playback_advances_to_next_segment(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    session = FakeSession()
    paths = [tmp_path / "000000.mp4", tmp_path / "000001.mp4"]
    for path in paths:
        path.write_bytes(b"mp4")
    session.recorder.recordings = [
        Recording("session", "drive", "2026-09-24", [
            Segment(paths[0], 0, 2), Segment(paths[1], 2, 4)
        ])
    ]
    window = DashPiWindow(session, IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        window.show_records()
        window._open_record(window.record_list.item(0))
        window._advance_on_end(QMediaPlayer.MediaStatus.EndOfMedia)
        assert window.player.source().toLocalFile() == str(paths[1])
    finally:
        window.close()


def test_open_incident_does_not_hash_video_on_ui_thread(qapp, tmp_path, monkeypatch):
    import dashpi.desktop as desktop

    store = IncidentStore(tmp_path)
    incident = IncidentMetadata.new("incident-async", datetime.now(UTC).isoformat(), 100.0, 15.0)
    incident.transition(IncidentState.ANALYSIS_FAILED, datetime.now(UTC).isoformat(), "AI unavailable")
    incident.clip = atomic_write(store.directory(incident.incident_id) / "clip.mp4", b"evidence")
    store.save(incident)
    gate = Event()
    original = desktop._open_verified_file

    def held_open(*args):
        if args[1] == "clip.mp4":
            gate.wait(1)
        return original(*args)

    monkeypatch.setattr(desktop, "_open_verified_file", held_open)
    window = desktop.DashPiWindow(FakeSession(), store, tmp_path / "settings.json")
    try:
        window.show_records()
        window._open_record(window.record_list.item(0))
        assert window.segment_list.count() == 0
        gate.set()
        wait_until(qapp, lambda: window.segment_list.count() == 1)
    finally:
        gate.set()
        window.close()


def test_verified_clip_is_kept_while_optical_page_is_open(qapp, tmp_path, monkeypatch):
    import dashpi.desktop as desktop

    store = IncidentStore(tmp_path)
    incident = IncidentMetadata.new("incident-qr-switch", datetime.now(UTC).isoformat(), 100.0, 15.0)
    incident.transition(IncidentState.READY, datetime.now(UTC).isoformat())
    directory = store.directory(incident.incident_id)
    incident.clip = atomic_write(directory / "clip.mp4", b"evidence")
    incident.report_html = atomic_write(directory / "report.html", b"<html>report</html>")
    store.save(incident)
    gate = Event()
    original = desktop._open_verified_file

    def held_open(*args):
        if args[1] == "clip.mp4":
            gate.wait(1)
        return original(*args)

    monkeypatch.setattr(desktop, "_open_verified_file", held_open)
    window = desktop.DashPiWindow(FakeSession(), store, tmp_path / "settings.json")
    try:
        window.show_records()
        window._open_record(window.record_list.item(0))
        window.start_optical(incident)
        gate.set()
        wait_until(qapp, lambda: window.optical_session is not None)
        window._leave_optical()
        assert window.segment_list.count() == 1
    finally:
        gate.set()
        window.close()


def test_stop_after_camera_failure_returns_home(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    session = FakeSession()
    session.last_error = "camera disconnected"
    window = DashPiWindow(session, IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        window.show_recording()
        window.stop_button.click()
        wait_until(qapp, lambda: window.pages.currentWidget() is window.home)
        assert "camera disconnected" in window.home_status.text()
    finally:
        window.close()


def test_qr_render_skips_a_bad_frame_and_keeps_transfer_running(qapp, tmp_path, monkeypatch):
    import qrcode
    from dashpi.desktop import DashPiWindow

    window = DashPiWindow(FakeSession(), IncidentStore(tmp_path), tmp_path / "settings.json")
    window.optical_session = OpticalSession.from_bytes("report.html", b"report", "text/html", 512, 123)
    original = qrcode.QRCode.make
    failed = False

    def fail_once(self, *args, **kwargs):
        nonlocal failed
        if not failed:
            failed = True
            raise ValueError("glog(0)")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(qrcode.QRCode, "make", fail_once)
    try:
        window._render_optical_frame()
        assert window._optical_sequence == 1
        window._render_optical_frame()
        assert window.qr_label.pixmap() is not None
    finally:
        window.close()


def test_stop_during_post_window_shows_pending_state(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    session = FakeSession()
    session.pending_stop = True
    session.recorder.recording = True
    window = DashPiWindow(session, IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        window.show_recording()
        window.stop_button.setEnabled(True)
        window.recording_controls()[1].click()
        wait_until(qapp, lambda: "15초" in window.record_status.text())
        assert session.pending_stop
    finally:
        session.pending_stop = False
        window.close()


def test_trigger_uses_button_press_time_even_if_camera_worker_is_busy(qapp, tmp_path, monkeypatch):
    import dashpi.desktop as desktop

    session = FakeSession()
    session.recorder.recording = True
    window = desktop.DashPiWindow(session, IncidentStore(tmp_path), tmp_path / "settings.json")
    gate = Event()
    try:
        window.timer.stop()
        window.analyze_button.setEnabled(True)
        window._executor.submit(lambda: gate.wait(1))
        monkeypatch.setattr(desktop, "time", SimpleNamespace(monotonic=lambda: 100.0))
        window._trigger()
        monkeypatch.setattr(desktop, "time", SimpleNamespace(monotonic=lambda: 200.0))
        gate.set()
        wait_until(qapp, lambda: hasattr(session, "trigger_at"))
        assert session.trigger_at == 100.0
    finally:
        gate.set()
        window.close()


def test_capture_controls_wait_for_first_recorded_frame(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    gate = Event()

    class SlowSession(FakeSession):
        def start(self, mode):
            gate.wait(1)
            super().start(mode)

    session = SlowSession()
    window = DashPiWindow(session, IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        window._begin("drive")
        wait_until(qapp, lambda: session.recorder.prepared)
        qapp.processEvents()
        assert not window.analyze_button.isEnabled()
        assert not window.stop_button.isEnabled()
        gate.set()
        wait_until(qapp, lambda: window.record_status.text() == "녹화 중")
        assert all(control.isEnabled() for control in window.recording_controls())
    finally:
        gate.set()
        session.recorder.recording = False
        window.close()


def test_recording_header_tracks_actual_capture_state(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    session = FakeSession()
    window = DashPiWindow(session, IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        assert "REC" not in window.record_heading.text()
        session.recorder.recording = True
        window._poll()
        assert "REC" in window.record_heading.text()
        assert len(window.record_clock.text()) == 5
        session.recorder.recording = False
        window._poll()
        assert "REC" not in window.record_heading.text()
    finally:
        session.recorder.recording = False
        window.close()


def test_failed_capture_start_releases_prepared_camera(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    class FailedSession(FakeSession):
        def start(self, mode):
            raise RuntimeError("disk full")

    session = FailedSession()
    window = DashPiWindow(session, IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        window._begin("drive")
        wait_until(qapp, lambda: "disk full" in window.record_status.text())
        wait_until(qapp, lambda: not session.recorder.prepared)
        assert session.recorder.picam2 is None
    finally:
        window.close()


def test_capture_can_retry_after_failed_start(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    class FailOnceSession(FakeSession):
        attempts = 0

        def start(self, mode):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("disk full")
            super().start(mode)

    session = FailOnceSession()
    window = DashPiWindow(session, IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        window._begin("drive")
        wait_until(qapp, lambda: "disk full" in window.record_status.text())
        wait_until(qapp, lambda: not session.recorder.prepared)
        window._begin("drive")
        wait_until(qapp, lambda: window.record_status.text() == "녹화 중")
        assert session.attempts == 2
    finally:
        session.recorder.recording = False
        window.close()


def test_close_during_camera_start_waits_then_stops_capture(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    entered, gate = Event(), Event()

    class SlowSession(FakeSession):
        def start(self, mode):
            entered.set()
            gate.wait(1)
            super().start(mode)

    session = SlowSession()
    window = DashPiWindow(session, IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        window._begin("drive")
        wait_until(qapp, entered.is_set)
        window.close()
        assert window.timer.isActive()
        gate.set()
        wait_until(qapp, lambda: not window.timer.isActive())
        assert not session.recorder.recording
        assert session.stop_count == 1
    finally:
        gate.set()
        session.recorder.recording = False
        window.close()


def test_double_start_tap_does_not_prepare_camera_twice(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    gate = Event()

    class SlowSession(FakeSession):
        def start(self, mode):
            gate.wait(1)
            super().start(mode)

    session = SlowSession()
    window = DashPiWindow(session, IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        window._begin("drive")
        window._begin("drive")
        gate.set()
        wait_until(qapp, lambda: window.record_status.text() == "녹화 중")
        assert session.recorder.prepare_count == 1
        assert session.start_count == 1
    finally:
        gate.set()
        session.recorder.recording = False
        window.close()


def test_bad_settings_do_not_trap_window_in_starting_state(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    path = tmp_path / "settings.json"
    window = DashPiWindow(FakeSession(), IncidentStore(tmp_path), path)
    path.write_text("not json")
    try:
        window._begin("drive")
        assert not window._starting
        assert window.stop_button.isEnabled()
        window.close()
        assert not window.timer.isActive()
    finally:
        window.close()


def test_record_detail_rejects_tampered_report(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("incident-1", datetime.now(UTC).isoformat(), 100.0, 15.0)
    item.transition(IncidentState.READY, datetime.now(UTC).isoformat())
    report_path = store.directory(item.incident_id) / "report.json"
    item.report_json = atomic_write(report_path, json.dumps({"summary": "verified"}).encode())
    store.save(item)
    report_path.write_text(json.dumps({"summary": "forged"}))
    window = DashPiWindow(FakeSession(), store, tmp_path / "settings.json")
    try:
        window.show_records()
        window._open_record(window.record_list.item(0))
        assert "forged" not in window.report_text.text()
        assert "검증" in window.report_text.text()
    finally:
        window.close()


def test_record_detail_displays_verified_summary(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("incident-2", datetime.now(UTC).isoformat(), 100.0, 15.0)
    item.transition(IncidentState.READY, datetime.now(UTC).isoformat())
    item.report_json = atomic_write(
        store.directory(item.incident_id) / "report.json",
        json.dumps({"summary": "verified summary"}).encode(),
    )
    store.save(item)
    window = DashPiWindow(FakeSession(), store, tmp_path / "settings.json")
    try:
        window.show_records()
        window._open_record(window.record_list.item(0))
        assert window.report_text.text() == "verified summary"
    finally:
        window.close()


def test_record_detail_displays_observations_and_limitations(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("incident-3", datetime.now(UTC).isoformat(), 100.0, 15.0)
    item.transition(IncidentState.READY, datetime.now(UTC).isoformat())
    item.report_json = atomic_write(
        store.directory(item.incident_id) / "report.json",
        json.dumps({"summary": "접촉 가능성", "incident_timestamp": 10.5,
                    "observations": [{"timestamp": 10.5, "description": "차량 접근"}],
                    "limitations": ["영상만으로 과실 판단 불가"]}).encode(),
    )
    store.save(item)
    window = DashPiWindow(FakeSession(), store, tmp_path / "settings.json")
    try:
        window.show_records()
        window._open_record(window.record_list.item(0))
        assert "접촉 가능성" in window.report_text.text()
        assert "10.5초 · 차량 접근" in window.report_text.text()
        assert "영상만으로 과실 판단 불가" in window.report_text.text()
    finally:
        window.close()


def test_repeated_close_does_not_queue_duplicate_stop(qapp, tmp_path):
    session = FakeSession()
    session.recorder.recording = True
    from dashpi.desktop import DashPiWindow

    window = DashPiWindow(session, IncidentStore(tmp_path), tmp_path / "settings.json")
    gate = Event()
    try:
        window.timer.stop()
        window._executor.submit(lambda: gate.wait(1))
        window.close()
        window.close()
        assert len(window._jobs) == 1
    finally:
        gate.set()
        session.recorder.recording = False
        window.close()


def test_native_optical_screen_sends_verified_report(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("incident-1", datetime.now(UTC).isoformat(), 100.0, 15.0)
    item.transition(IncidentState.READY, datetime.now(UTC).isoformat())
    payload = b"<html>DashPi report</html>"
    item.report_html = atomic_write(store.directory(item.incident_id) / "report.html", payload)
    store.save(item)
    window = DashPiWindow(FakeSession(), store, tmp_path / "settings.json")
    try:
        window.start_optical(item)
        wait_until(qapp, lambda: window.optical_session is not None)
        assert window.pages.currentWidget() is window.optical_page
        assert window.qr_label.pixmap() is not None
        frame = parse_frame(window.optical_session.frame(0))
        decoder = FountainDecoder(frame.block_count, frame.block_size, frame.total_length)
        decoder.add(frame.indices, frame.symbol)
        assert unpack_container(decoder.result()).payload == payload
    finally:
        window.close()


def test_native_optical_screen_rejects_tampered_or_oversize_report(qapp, tmp_path, monkeypatch):
    import dashpi.desktop as desktop

    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("incident-1", datetime.now(UTC).isoformat(), 100.0, 15.0)
    item.transition(IncidentState.READY, datetime.now(UTC).isoformat())
    path = store.directory(item.incident_id) / "report.html"
    item.report_html = atomic_write(path, b"verified report")
    store.save(item)
    window = desktop.DashPiWindow(FakeSession(), store, tmp_path / "settings.json")
    try:
        path.write_bytes(b"forged report")
        window.start_optical(item)
        wait_until(qapp, lambda: "검증" in window.optical_status.text())
        assert window.optical_session is None
        assert "검증" in window.optical_status.text()
        item.report_html = atomic_write(path, b"verified report")
        store.save(item)
        monkeypatch.setattr(desktop, "MAX_PAYLOAD", 5)
        window.start_optical(item)
        wait_until(qapp, lambda: "16 MiB" in window.optical_status.text())
        assert window.optical_session is None
        assert "16 MiB" in window.optical_status.text()
    finally:
        window.close()


def test_optical_preparation_does_not_read_report_on_ui_thread(qapp, tmp_path, monkeypatch):
    import dashpi.desktop as desktop

    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("incident-optical", datetime.now(UTC).isoformat(), 100.0, 15.0)
    item.transition(IncidentState.READY, datetime.now(UTC).isoformat())
    item.report_html = atomic_write(store.directory(item.incident_id) / "report.html", b"<html>report</html>")
    store.save(item)
    gate = Event()
    original = desktop._open_verified_file

    def held_open(*args):
        if args[1] == "report.html":
            gate.wait(1)
        return original(*args)

    monkeypatch.setattr(desktop, "_open_verified_file", held_open)
    window = desktop.DashPiWindow(FakeSession(), store, tmp_path / "settings.json")
    try:
        window.start_optical(item)
        assert window.optical_session is None
        assert "준비 중" in window.optical_status.text()
        gate.set()
        wait_until(qapp, lambda: window.optical_session is not None)
    finally:
        gate.set()
        window.close()


def test_camera_failure_stays_visible_instead_of_silently_returning_home(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    class FailedSession(FakeSession):
        def tick(self, now):
            self.last_error = "camera disconnected"
            self.recorder.recording = False

    session = FailedSession()
    window = DashPiWindow(session, IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        window.show_recording()
        session.recorder.recording = True
        wait_until(qapp, lambda: hasattr(session, "last_error"))
        wait_until(qapp, lambda: "camera disconnected" in window.record_status.text())
        assert window.pages.currentWidget() is window.recording_page
    finally:
        session.recorder.recording = False
        window.close()


@pytest.mark.parametrize("size", [(480, 320), (800, 480), (1920, 1080)])
def test_home_tiles_share_the_screen_at_any_lcd_size(qapp, tmp_path, size):
    from dashpi.desktop import DashPiWindow

    window = DashPiWindow(FakeSession(), IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        window.showNormal()
        window.setFixedSize(*size)
        qapp.processEvents()
        tiles = window.home.findChildren(QToolButton)
        width, height = size
        assert all(tile.geometry().right() < width and tile.geometry().bottom() < height for tile in tiles)
        assert all(tile.width() > width / 4 and tile.height() > height / 3 for tile in tiles)
    finally:
        window.close()
