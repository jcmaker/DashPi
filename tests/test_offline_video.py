import json

from dashpi.config import Settings
from dashpi.media import probe_duration
from dashpi.models import IncidentState
from dashpi.storage import IncidentStore, sha256_file
from tests.media_factory import make_video


def test_short_external_video_uses_available_footage_and_keeps_original(tmp_path):
    from dashpi.offline_video import analyze_external_video

    source = make_video(tmp_path / "source.mp4", 12)
    original_hash = sha256_file(source)
    settings = Settings(tmp_path / "data", "test-model", frame_sample_count=3)
    store = IncidentStore(settings.data_root)

    result = analyze_external_video(
        source, 5.0, settings, store,
        lambda *_: {
            "incident_timestamp": 5.0,
            "summary": "사고 장면",
            "observations": [],
            "limitations": ["영상만 분석"],
        },
    )

    assert result.state is IncidentState.READY
    assert sha256_file(source) == original_hash
    assert 11.9 <= probe_duration(result.clip.path) <= 12.1
    assert result.incident_offset_seconds == 5.0
    assert result.report_html.path.is_file()
    assert json.loads(result.report_json.path.read_text())["incident_timestamp"] == 5.0


def test_external_video_rejects_missing_file_without_incident(tmp_path):
    import pytest
    from dashpi.offline_video import analyze_external_video

    settings = Settings(tmp_path / "data", "test-model")
    store = IncidentStore(settings.data_root)
    with pytest.raises(FileNotFoundError):
        analyze_external_video(tmp_path / "gone.mp4", 2.0, settings, store, lambda *_: {})
    assert store.list() == []
