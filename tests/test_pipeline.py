import pytest

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
