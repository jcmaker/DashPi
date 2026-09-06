from argparse import Namespace
from dataclasses import replace
from threading import Event

import pytest

import dashpi.server as server_module
from dashpi.analysis_worker import AnalysisWorker
from dashpi.config import OverlaySettings
from dashpi.models import IncidentState
from dashpi.storage import atomic_write, sha256_file
from tests.test_api import ready_store_with_clip
from tests.media_factory import make_video


def run_server(monkeypatch, tmp_path, exercise, analyze):
    args = Namespace(data_root=tmp_path, host="127.0.0.1", port=8000,
                     ollama_model="vision", detector_model=tmp_path / "yolo.pt",
                     show_traffic_lights=False, show_lanes=False, show_traffic_signs=False)
    worker = AnalysisWorker()
    captured = {}
    real_create_app = server_module.create_app

    def create_app(store, regenerate_report):
        captured["regenerate"] = regenerate_report
        return real_create_app(store, regenerate_report)

    monkeypatch.setattr(server_module, "build_parser", lambda: type("Parser", (), {"parse_args": lambda self: args})())
    monkeypatch.setattr(server_module, "AnalysisWorker", lambda: worker)
    monkeypatch.setattr(server_module, "YoloDetector", lambda *_: None)
    monkeypatch.setattr(server_module, "OllamaClient", lambda *_: type("Client", (), {"analyze": staticmethod(analyze)})())
    monkeypatch.setattr(server_module, "create_app", create_app)
    monkeypatch.setattr(server_module.uvicorn, "run", lambda *_a, **_kw: exercise(captured["regenerate"], worker))
    try:
        server_module.main()
    finally:
        worker.close()


@pytest.mark.parametrize("damage", ["outside", "clip_symlink", "directory_symlink"])
def test_queued_regeneration_revalidates_clip_before_analysis(tmp_path, monkeypatch, damage):
    store, item = ready_store_with_clip(tmp_path, 6.0)
    sampled = []
    monkeypatch.setattr("dashpi.pipeline.sample_frames", lambda path, *_: sampled.append(path.read_bytes()) or [])

    def exercise(regenerate, worker):
        worker.pause()
        worker.submit(worker.wait_for_capacity)
        future = regenerate(item, None, OverlaySettings())
        if damage == "outside":
            item.clip = replace(atomic_write(tmp_path / "outside.mp4", b"clip"), duration=6.0)
            store.save(item)
        elif damage == "clip_symlink":
            outside = atomic_write(tmp_path / "outside.mp4", b"clip")
            item.clip.path.unlink()
            item.clip.path.symlink_to(outside.path)
        else:
            directory = store.directory(item.incident_id)
            directory.rename(tmp_path / "outside")
            directory.symlink_to(tmp_path / "outside", target_is_directory=True)
        worker.resume()
        try:
            future.result(timeout=5)
        except Exception:
            pass  # A rejected trust-boundary check may fail the Future.
        assert sampled == []

    run_server(monkeypatch, tmp_path, exercise, lambda _frames: {})


def test_queued_regeneration_reloads_the_latest_completed_metadata(tmp_path, monkeypatch):
    store, item = ready_store_with_clip(tmp_path, 6.0)
    video = make_video(tmp_path / "source.mp4", 6)
    item.clip = replace(atomic_write(item.clip.path, video.read_bytes()), duration=6.0)
    store.save(item)
    stale = store.load(item.incident_id)
    reports = iter([
        {"incident_timestamp": 1.0, "summary": "new", "observations": [], "limitations": []},
        {"summary": "invalid"},
    ])

    def exercise(regenerate, worker):
        worker.pause()
        worker.submit(worker.wait_for_capacity)
        first = regenerate(item, None, OverlaySettings())
        second = regenerate(stale, None, OverlaySettings())
        worker.resume()
        completed = first.result(timeout=20)
        failed = second.result(timeout=20)
        assert completed.state is IncidentState.READY, completed.failure_reason
        assert failed.state is IncidentState.ANALYSIS_FAILED
        saved = store.load(item.incident_id)
        assert saved.report_html.sha256 == sha256_file(saved.report_html.path)
        assert saved.annotated == completed.annotated
        assert saved.transitions[:-2] == completed.transitions

    run_server(monkeypatch, tmp_path, exercise, lambda _frames: next(reports))


@pytest.mark.parametrize("replacement", ["clip", "directory"])
def test_regeneration_media_reads_verified_snapshot_after_path_replacement(tmp_path, monkeypatch, replacement):
    store, item = ready_store_with_clip(tmp_path, 6.0)
    entered, resume = Event(), Event()
    sources = []
    real_save = store.__class__.save

    def save_and_pause(self, current):
        real_save(self, current)
        if current.state is IncidentState.ANALYZING:
            entered.set()
            assert resume.wait(5)

    monkeypatch.setattr(store.__class__, "save", save_and_pause)
    monkeypatch.setattr("dashpi.pipeline.sample_frames", lambda path, *_: sources.append(path) or [path.read_bytes()])

    def exercise(regenerate, _worker):
        future = regenerate(item, None, OverlaySettings())
        try:
            assert entered.wait(5)
            if replacement == "directory":
                directory = store.directory(item.incident_id)
                directory.rename(tmp_path / "original")
                directory.mkdir()
            atomic_write(item.clip.path, b"evil")
        finally:
            resume.set()
        result = future.result(timeout=5)
        assert result.failure_reason == "verified bytes: clip"
        assert all(not path.exists() for path in sources)

    def analyze(frames):
        raise ValueError("verified bytes: " + frames[0].decode())

    run_server(monkeypatch, tmp_path, exercise, analyze)


def test_regeneration_detects_in_place_evidence_changes_during_analysis(tmp_path, monkeypatch):
    store, item = ready_store_with_clip(tmp_path, 6.0)
    video = make_video(tmp_path / "source.mp4", 6)
    item.clip = replace(atomic_write(item.clip.path, video.read_bytes()), duration=6.0)
    store.save(item)

    def analyze(_frames):
        with item.clip.path.open("r+b") as source:
            source.write(b"evil")
        return {"incident_timestamp": 1.0, "summary": "new", "observations": [], "limitations": []}

    def exercise(regenerate, _worker):
        result = regenerate(item, None, OverlaySettings()).result(timeout=20)
        assert result.state is IncidentState.ANALYSIS_FAILED
        assert result.failure_reason == "clip digest changed"
        assert result.annotated.sha256 == sha256_file(result.annotated.path)

    run_server(monkeypatch, tmp_path, exercise, analyze)
