from dashpi.models import FileArtifact, IncidentMetadata, IncidentState


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
