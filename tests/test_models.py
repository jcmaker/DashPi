import json

from dashpi.models import FileArtifact, IncidentMetadata, IncidentState
from dashpi.storage import IncidentStore


def test_new_incident_starts_collecting():
    incident = IncidentMetadata.new("inc-1", wall_time="2026-09-02T00:00:00Z", trigger_mono=40.0, post_seconds=15.0)
    assert incident.state is IncidentState.COLLECTING_POST_TRIGGER
    assert incident.post_deadline_mono == 55.0
    assert incident.transitions == [{"state": "collecting_post_trigger", "at": "2026-09-02T00:00:00Z"}]


def test_incident_metadata_includes_configured_windows_and_artifact_contract(tmp_path):
    incident = IncidentMetadata.new(
        "inc-1", "2026-09-02T00:00:00Z", 40.0, post_seconds=15.0, pre_seconds=30.0
    )
    incident.clip = FileArtifact(tmp_path / "clip.mp4", 42, "clip-digest", duration=44.9)
    incident.report_json = FileArtifact(tmp_path / "report.json", 7, "json-digest")
    incident.report_html = FileArtifact(tmp_path / "report.html", 8, "html-digest")
    incident.report_model = "moondream"
    incident.report_generated_at = "2026-09-02T00:01:00Z"
    incident.transition(IncidentState.READY, "2026-09-02T00:01:01Z")

    assert incident.to_dict() == {
        "incident_id": "inc-1",
        "triggered_at": "2026-09-02T00:00:00Z",
        "trigger_mono": 40.0,
        "pre_seconds": 30.0,
        "post_seconds": 15.0,
        "incident_offset_seconds": None,
        "post_deadline_mono": 55.0,
        "state": IncidentState.READY,
        "failure_reason": None,
        "clip": {
            "filename": "clip.mp4",
            "path": str(tmp_path / "clip.mp4"),
            "byte_length": 42,
            "sha256": "clip-digest",
            "duration": 44.9,
        },
        "annotated": None,
        "report_json": {
            "filename": "report.json",
            "path": str(tmp_path / "report.json"),
            "byte_length": 7,
            "sha256": "json-digest",
            "duration": None,
        },
        "report_html": {
            "filename": "report.html",
            "path": str(tmp_path / "report.html"),
            "byte_length": 8,
            "sha256": "html-digest",
            "duration": None,
        },
        "report_model": "moondream",
        "report_generated_at": "2026-09-02T00:01:00Z",
        "analysis_attempts": 0,
        "next_analysis_at": None,
        "transitions": [
            {"state": "collecting_post_trigger", "at": "2026-09-02T00:00:00Z"},
            {"state": "ready", "at": "2026-09-02T00:01:01Z"},
        ],
    }


def test_incident_metadata_serializes_derived_artifact_and_localized_time(tmp_path):
    item = IncidentMetadata.new("inc-1", "2026-09-06T00:00:00Z", 40.0, 15.0)
    item.annotated = FileArtifact(tmp_path / "annotated.mp4", 3, "abc", 10.0)
    item.incident_offset_seconds = 29.5

    raw = item.to_dict()

    assert raw["annotated"]["filename"] == "annotated.mp4"
    assert raw["incident_offset_seconds"] == 29.5


def test_awaiting_analysis_round_trips_with_retry_fields(tmp_path):
    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("inc-1", "2026-09-25T00:00:00+00:00", 10.0, 15.0)
    item.analysis_attempts = 2
    item.next_analysis_at = "2026-09-25T00:05:00+00:00"
    item.transition(IncidentState.AWAITING_ANALYSIS, "2026-09-25T00:03:00+00:00", "인터넷 연결 없음")
    store.save(item)

    loaded = store.load("inc-1")
    assert loaded.state is IncidentState.AWAITING_ANALYSIS
    assert (loaded.analysis_attempts, loaded.next_analysis_at) == (2, "2026-09-25T00:05:00+00:00")
    assert loaded.failure_reason == "인터넷 연결 없음"


def test_metadata_written_before_retry_fields_still_loads(tmp_path):
    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("old", "2026-09-24T00:00:00+00:00", 10.0, 15.0)
    store.save(item)
    path = store.directory("old") / "metadata.json"
    raw = json.loads(path.read_text())
    del raw["analysis_attempts"], raw["next_analysis_at"]
    path.write_text(json.dumps(raw))

    loaded = store.load("old")
    assert (loaded.analysis_attempts, loaded.next_analysis_at) == (0, None)
