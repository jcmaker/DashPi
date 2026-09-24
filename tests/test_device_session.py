import os
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import Future

import pytest

from dashpi.config import Settings
from dashpi.models import IncidentState, Segment
from dashpi.storage import IncidentStore


class FakeRecorder:
    segment_seconds = 2.0
    start_mono = 50.0

    def __init__(self, root: Path):
        self.root = root
        self.recording = False
        self.now = 100.0
        first = root / "raw" / "session" / "000000.mp4"
        first.parent.mkdir(parents=True)
        first.write_bytes(b"raw video")
        self.session_dir = first.parent
        self.segments = [Segment(first, 50.0, 100.0)]
        self.fail_split = False
        self.allowed_empty_tail = False

    def start(self, mode):
        self.mode = mode
        self.recording = True

    def split(self):
        if self.fail_split:
            raise RuntimeError("camera disconnected")
        start = self.segments[-1].end_mono
        if self.now > start:
            path = self.segments[-1].path.with_name(f"{len(self.segments):06d}.mp4")
            path.write_bytes(b"raw video")
            self.segments.append(Segment(path, start, self.now))
        return self.segments

    def stop(self, *, allow_empty_tail=False):
        self.allowed_empty_tail = allow_empty_tail
        self.recording = False
        return self.segments


class InlineWorker:
    def submit(self, work):
        return work()


def make_session(tmp_path, recorder, monkeypatch, processed):
    from dashpi.device_session import DeviceSession

    class Pipeline:
        def __init__(self, settings, store, detector=None):
            pass

        def process(self, incident, segments, analyze):
            processed.append((incident, list(segments)))
            return incident

    monkeypatch.setattr("dashpi.device_session.IncidentPipeline", Pipeline)
    settings = Settings(tmp_path, "fake", pre_seconds=30, post_seconds=15)
    return DeviceSession(recorder, settings, IncidentStore(tmp_path), InlineWorker(), lambda frames: {})


def test_stop_waits_for_post_window_and_submits_complete_window(tmp_path, monkeypatch):
    recorder = FakeRecorder(tmp_path)
    processed = []
    session = make_session(tmp_path, recorder, monkeypatch, processed)
    session.start("drive")
    incident = session.trigger(100.0)

    assert session.stop(101.0) is False
    assert session.pending_stop
    recorder.now = 114.9
    session.tick(114.9)
    assert recorder.recording and not processed
    recorder.now = 115.1
    session.tick(115.1)

    assert not recorder.recording
    assert not session.pending_stop
    assert recorder.allowed_empty_tail
    assert len(processed) == 1
    assert processed[0][0].incident_id == incident.incident_id
    assert processed[0][1][-1].end_mono >= 115.0


def test_camera_failure_marks_incomplete_incident_and_keeps_raw(tmp_path, monkeypatch):
    recorder = FakeRecorder(tmp_path)
    processed = []
    session = make_session(tmp_path, recorder, monkeypatch, processed)
    session.start("drive")
    incident = session.trigger(100.0)
    recorder.fail_split = True

    session.tick(110.0)

    saved = IncidentStore(tmp_path).load(incident.incident_id)
    assert saved.state is IncidentState.CLIP_FAILED
    assert "incomplete" in saved.failure_reason
    assert recorder.segments[0].path.exists()
    assert not recorder.recording
    assert not processed


def test_pruning_removes_old_raw_but_protects_incident_and_saved_clip(tmp_path, monkeypatch):
    recorder = FakeRecorder(tmp_path)
    processed = []
    session = make_session(tmp_path, recorder, monkeypatch, processed)
    old = tmp_path / "raw" / "previous" / "000000.mp4"
    old.parent.mkdir()
    old.write_bytes(b"x" * 100)
    os.utime(old, (1, 1))
    saved = tmp_path / "incidents" / "saved" / "clip.mp4"
    saved.parent.mkdir(parents=True)
    saved.write_bytes(b"saved evidence")
    monkeypatch.setattr(
        "shutil.disk_usage",
        lambda path: SimpleNamespace(total=1000, used=300, free=700),
    )
    session.settings = Settings(tmp_path, "fake", raw_max_fraction=0.1)
    session.start("drive")
    session.trigger(100.0)

    session.prune_raw(100.0)

    assert not old.exists()
    assert recorder.segments[0].path.exists()
    assert saved.read_bytes() == b"saved evidence"


def test_pending_clip_job_protects_its_source_segments(tmp_path, monkeypatch):
    recorder = FakeRecorder(tmp_path)
    session = make_session(tmp_path, recorder, monkeypatch, [])

    class PendingWorker:
        def submit(self, work):
            return Future()

    session.worker = PendingWorker()
    session.start("drive")
    session.trigger(100.0)
    recorder.now = 115.1
    session.tick(115.1)
    evidence_sources = [segment.path for segment in recorder.segments]
    old = tmp_path / "raw" / "previous" / "000000.mp4"
    old.parent.mkdir()
    old.write_bytes(b"x" * 100)
    os.utime(old, (1, 1))
    monkeypatch.setattr(
        "shutil.disk_usage",
        lambda path: SimpleNamespace(total=1000, used=300, free=700),
    )
    session.settings = Settings(tmp_path, "fake", raw_max_fraction=0.01)

    assert session.prune_raw(200.0) is False
    assert not old.exists()
    assert all(path.exists() for path in evidence_sources)


def test_incomplete_capture_keeps_raw_across_later_pruning(tmp_path, monkeypatch):
    recorder = FakeRecorder(tmp_path)
    session = make_session(tmp_path, recorder, monkeypatch, [])
    session.start("drive")
    session.trigger(100.0)
    recorder.fail_split = True
    session.tick(110.0)
    old = tmp_path / "raw" / "previous" / "000000.mp4"
    old.parent.mkdir()
    old.write_bytes(b"x" * 100)
    os.utime(old, (1, 1))
    monkeypatch.setattr(
        "shutil.disk_usage",
        lambda path: SimpleNamespace(total=1000, used=300, free=700),
    )
    session.settings = Settings(tmp_path, "fake", raw_max_fraction=0.001)

    assert session.prune_raw(200.0) is False
    assert (recorder.session_dir / "incomplete_capture.txt").is_file()
    assert recorder.segments[0].path.exists()
    assert not old.exists()


def test_trigger_before_first_capture_frame_is_rejected(tmp_path, monkeypatch):
    recorder = FakeRecorder(tmp_path)
    session = make_session(tmp_path, recorder, monkeypatch, [])
    session.start("drive")

    with pytest.raises(RuntimeError, match="녹화 시작 전"):
        session.trigger(recorder.start_mono - 0.1)
    assert session.coordinator.active == []


def test_post_window_waits_for_recorded_frame_coverage(tmp_path, monkeypatch):
    recorder = FakeRecorder(tmp_path)
    processed = []
    session = make_session(tmp_path, recorder, monkeypatch, processed)
    session.start("drive")
    session.trigger(100.0)
    assert session.stop(101.0) is False

    recorder.now = 114.9
    session.tick(115.1)
    assert recorder.recording
    assert not processed

    recorder.now = 117.2
    session.tick(117.2)
    assert not recorder.recording
    assert len(processed) == 1
    assert processed[0][1][-1].end_mono >= 115.0


def test_stop_at_post_deadline_tolerates_newly_opened_tail(tmp_path, monkeypatch):
    recorder = FakeRecorder(tmp_path)
    session = make_session(tmp_path, recorder, monkeypatch, [])
    session.start("drive")
    session.trigger(100.0)
    recorder.now = 115.1

    assert session.stop(115.1) is True
    assert recorder.allowed_empty_tail
