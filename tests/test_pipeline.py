import pytest
import json

from dashpi.config import Settings
from dashpi.models import IncidentMetadata, Segment
from dashpi.pipeline import IncidentPipeline
from dashpi.storage import IncidentStore
from tests.media_factory import make_video


@pytest.fixture
def pipeline_fixture(tmp_path):
    paths = [make_video(tmp_path / f"{index}.mp4", 2) for index in range(3)]
    segments = [Segment(path, index * 2.0, index * 2.0 + 2.0) for index, path in enumerate(paths)]
    settings = Settings(tmp_path / "data", "test-model")
    pipeline = IncidentPipeline(settings, IncidentStore(settings.data_root))
    incident = IncidentMetadata.new("inc-1", "2026-09-02T00:00:00Z", 3.0, settings.post_seconds)
    return pipeline, incident, segments


def test_pipeline_creates_clip_and_reports(pipeline_fixture):
    pipeline, incident, segments = pipeline_fixture

    result = pipeline.process(
        incident,
        segments,
        lambda frames: {"summary": "Stopped", "observations": [], "limitations": []},
    )

    assert result.state.value == "ready"
    assert result.clip.path.exists() and result.report_json.path.exists() and result.report_html.path.exists()


def test_ai_failure_preserves_clip(pipeline_fixture):
    pipeline, incident, segments = pipeline_fixture

    def fail(_frames):
        raise TimeoutError("model timeout")

    result = pipeline.process(incident, segments, fail)

    assert result.state.value == "analysis_failed"
    assert result.clip.path.exists()
    assert result.transitions[-1]["state"] == "analysis_failed"


def test_pipeline_records_clip_and_report_metadata_from_configured_window(tmp_path):
    paths = [make_video(tmp_path / f"{index}.mp4", 2) for index in range(3)]
    segments = [Segment(path, index * 2.0, index * 2.0 + 2.0) for index, path in enumerate(paths)]
    settings = Settings(tmp_path / "data", "test-model", pre_seconds=2.0, post_seconds=2.0)
    incident = IncidentMetadata.new(
        "inc-1", "2026-09-02T00:00:00Z", 3.0, settings.post_seconds, settings.pre_seconds
    )

    result = IncidentPipeline(settings, IncidentStore(settings.data_root)).process(
        incident,
        segments,
        lambda _frames: {"summary": "Stopped", "observations": [], "limitations": []},
    )

    assert (result.pre_seconds, result.post_seconds) == (2.0, 2.0)
    assert 3.8 <= result.clip.duration <= 4.2
    assert result.report_model == "test-model"
    assert result.report_generated_at
    report = json.loads(result.report_json.path.read_text())
    assert report["generated_at"] == result.report_generated_at
    assert report["model"] == result.report_model
    assert report["source_clip_sha256"] == result.clip.sha256


def test_sampling_failure_persists_exposed_clip(pipeline_fixture, monkeypatch):
    pipeline, incident, segments = pipeline_fixture

    def fail_sampling(*_args):
        raise RuntimeError("sampling failed")

    monkeypatch.setattr("dashpi.pipeline.sample_frames", fail_sampling)

    pipeline.process(incident, segments, lambda _frames: pytest.fail("analyzer should not run"))
    reloaded = pipeline.store.load(incident.incident_id)

    assert reloaded.state.value == "analysis_failed"
    assert reloaded.clip.path.exists()


def test_invalid_report_persists_exposed_clip(pipeline_fixture):
    pipeline, incident, segments = pipeline_fixture

    pipeline.process(incident, segments, lambda _frames: {"summary": "missing lists"})
    reloaded = pipeline.store.load(incident.incident_id)

    assert reloaded.state.value == "analysis_failed"
    assert reloaded.clip.path.exists()


def test_report_write_failure_persists_exposed_clip(pipeline_fixture, monkeypatch):
    pipeline, incident, segments = pipeline_fixture
    from dashpi.storage import atomic_write as real_atomic_write

    def fail_report_json(path, data):
        if path.name == "report.json":
            raise OSError("report disk failure")
        return real_atomic_write(path, data)

    monkeypatch.setattr("dashpi.pipeline.atomic_write", fail_report_json)

    pipeline.process(
        incident,
        segments,
        lambda _frames: {"summary": "Stopped", "observations": [], "limitations": []},
    )
    reloaded = pipeline.store.load(incident.incident_id)

    assert reloaded.state.value == "analysis_failed"
    assert reloaded.clip.path.exists()
