import time
from threading import Event
from types import SimpleNamespace
from datetime import UTC, datetime
import json

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QToolButton

from dashpi.device import VideoSettings, load_settings
from dashpi.models import IncidentMetadata, IncidentState
from dashpi.storage import IncidentStore, atomic_write


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class FakeRecorder:
    def __init__(self):
        self.recording = False
        self.picam2 = object()

    def prepare(self):
        pass

    def create_preview(self, parent=None):
        return QLabel("live camera", parent)

    def list_recordings(self):
        return []


class FakeSession:
    def __init__(self):
        self.recorder = FakeRecorder()
        self.pending_stop = False

    def start(self, mode):
        self.mode = mode
        self.recorder.recording = True

    def trigger(self, now):
        self.trigger_at = now
        self.pending_stop = True

    def stop(self, now):
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


def test_stop_during_post_window_shows_pending_state(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    session = FakeSession()
    session.pending_stop = True
    window = DashPiWindow(session, IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        window.show_recording()
        window.recording_controls()[1].click()
        wait_until(qapp, lambda: "15초" in window.record_status.text())
        assert session.pending_stop
    finally:
        session.pending_stop = False
        window.close()


def test_trigger_uses_button_press_time_even_if_camera_worker_is_busy(qapp, tmp_path, monkeypatch):
    import dashpi.desktop as desktop

    session = FakeSession()
    window = desktop.DashPiWindow(session, IncidentStore(tmp_path), tmp_path / "settings.json")
    gate = Event()
    try:
        window.timer.stop()
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
