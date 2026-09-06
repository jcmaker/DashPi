import pytest
import json

import dashpi.pipeline as pipeline_module
from dashpi.config import Settings
from dashpi.media import extract_frame, probe_duration, segment_source, transcode_clip
from dashpi.models import IncidentMetadata, IncidentState, Segment
from dashpi.optical.container import MAX_PAYLOAD
from dashpi.pipeline import IncidentPipeline
from dashpi.storage import IncidentStore, sha256_file
from tests.media_factory import make_video


@pytest.fixture
def pipeline_fixture(tmp_path):
    paths = [make_video(tmp_path / f"{index}.mp4", 2) for index in range(3)]
    segments = [Segment(path, index * 2.0, index * 2.0 + 2.0) for index, path in enumerate(paths)]
    settings = Settings(tmp_path / "data", "test-model")
    pipeline = IncidentPipeline(settings, IncidentStore(settings.data_root))
    incident = IncidentMetadata.new("inc-1", "2026-09-02T00:00:00Z", 3.0, settings.post_seconds)
    return pipeline, incident, segments


@pytest.fixture
def long_pipeline_fixture(tmp_path):
    source = make_video(tmp_path / "source.mp4", 46)
    segments = segment_source(source, tmp_path / "segments", 2.0)
    settings = Settings(tmp_path / "data", "test-model", pre_seconds=30.0, post_seconds=15.0)
    incident = IncidentMetadata.new(
        "inc-1", "2026-09-06T00:00:00Z", 30.0, settings.post_seconds, settings.pre_seconds
    )

    def detector(_frame):
        return [
            {"label": "car", "confidence": 0.91, "box": [20, 20, 90, 90]},
            {"label": "traffic light", "confidence": 0.82, "box": [100, 10, 125, 60]},
        ]

    pipeline = IncidentPipeline(settings, IncidentStore(settings.data_root), detector)
    return pipeline, incident, segments, detector


def localized_analysis(timestamp=3.0):
    return {
        "incident_timestamp": timestamp,
        "summary": "급정지 뒤 충돌",
        "observations": [{"timestamp": timestamp, "description": "차량 접촉"}],
        "limitations": ["단일 카메라"],
    }


def recording_transcode(real, calls):
    def wrapped(source, output, start, duration, height, bitrate):
        calls.append((source, output, start, duration, height, bitrate))
        return real(source, output, start, duration, height, bitrate)

    return wrapped


def test_oversized_html_reencodes_only_derivative_once(long_pipeline_fixture, monkeypatch):
    pipeline, incident, segments, _detector = long_pipeline_fixture
    sizes = iter([MAX_PAYLOAD + 1, MAX_PAYLOAD - 1])
    monkeypatch.setattr(pipeline_module, "render_report_html", lambda *args: "x" * next(sizes))
    calls = []
    monkeypatch.setattr(
        pipeline_module,
        "transcode_clip",
        recording_transcode(pipeline_module.transcode_clip, calls),
    )

    result = pipeline.process(incident, segments, lambda _frames: localized_analysis(22.5))

    assert calls[-1][0].name == "annotated.mp4"
    assert calls[-1][4:] == (360, "450k")
    assert result.report_html.byte_length <= MAX_PAYLOAD
    assert result.clip.sha256 == sha256_file(result.clip.path)


def test_second_size_failure_keeps_ready_report_for_local_wifi(long_pipeline_fixture, monkeypatch):
    pipeline, incident, segments, _detector = long_pipeline_fixture
    monkeypatch.setattr(pipeline_module, "render_report_html", lambda *args: "x" * (MAX_PAYLOAD + 1))

    result = pipeline.process(incident, segments, lambda _frames: localized_analysis(22.5))

    report = json.loads(result.report_json.path.read_text())
    assert result.state is IncidentState.READY
    assert result.report_html.byte_length > MAX_PAYLOAD
    assert "Optical payload exceeds 16 MiB; use Local Wi-Fi." in report["warnings"]


def test_pipeline_creates_ten_second_annotated_report_without_mutating_evidence(long_pipeline_fixture):
    pipeline, incident, segments, _detector = long_pipeline_fixture

    result = pipeline.process(incident, segments, lambda _frames: localized_analysis(22.5))

    assert result.state is IncidentState.READY
    assert result.annotated.path.name == "annotated.mp4"
    assert 9.9 <= result.annotated.duration <= 10.1
    assert result.clip.sha256 == sha256_file(result.clip.path)
    report = json.loads(result.report_json.path.read_text())
    assert report["transfer_window"] == {"start": 17.5, "end": 27.5}
    assert report["digests"]["clip.mp4"] == result.clip.sha256
    assert report["digests"]["annotated.mp4"] == result.annotated.sha256


def test_tracker_failure_creates_unannotated_ten_second_report_with_warning(
    long_pipeline_fixture, monkeypatch
):
    pipeline, incident, segments, _detector = long_pipeline_fixture
    monkeypatch.setattr(
        "dashpi.pipeline.annotate_clip",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("tracker failed")),
    )

    result = pipeline.process(incident, segments, lambda _frames: localized_analysis(22.5))

    assert result.state is IncidentState.READY
    assert 9.9 <= probe_duration(result.annotated.path) <= 10.1
    report = json.loads(result.report_json.path.read_text())
    assert report["object_observations"] == []
    assert "Object tracking failed; the transfer video has no boxes." in report["warnings"]


def test_short_successful_annotation_uses_ten_second_tracking_fallback(
    long_pipeline_fixture, monkeypatch
):
    pipeline, incident, segments, _detector = long_pipeline_fixture

    def short_annotation(
        source, output, start, duration, _incident_offset, _detector, _overlays, keyframe_dir, height, bitrate
    ):
        annotated = transcode_clip(source, output, start, duration / 2, height, bitrate)
        keyframes = [
            extract_frame(annotated.path, keyframe_dir / name, 1.0)
            for name in ("before.jpg", "moment.jpg", "after.jpg")
        ]
        return annotated, [], keyframes

    monkeypatch.setattr("dashpi.pipeline.annotate_clip", short_annotation)

    result = pipeline.process(incident, segments, lambda _frames: localized_analysis(22.5))

    assert result.state is IncidentState.READY
    assert 9.9 <= probe_duration(result.annotated.path) <= 10.1
    report = json.loads(result.report_json.path.read_text())
    assert "Object tracking failed; the transfer video has no boxes." in report["warnings"]


def test_pipeline_creates_clip_and_reports(pipeline_fixture):
    pipeline, incident, segments = pipeline_fixture

    result = pipeline.process(
        incident,
        segments,
        lambda frames: {"incident_timestamp": 3.0, "summary": "Stopped", "observations": [], "limitations": []},
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
        lambda _frames: {"incident_timestamp": 3.0, "summary": "Stopped", "observations": [], "limitations": []},
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
        lambda _frames: {"incident_timestamp": 3.0, "summary": "Stopped", "observations": [], "limitations": []},
    )
    reloaded = pipeline.store.load(incident.incident_id)

    assert reloaded.state.value == "analysis_failed"
    assert reloaded.clip.path.exists()
