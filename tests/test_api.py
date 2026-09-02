from fastapi.testclient import TestClient

from dashpi.api import create_app
from dashpi.models import IncidentMetadata, IncidentState
from dashpi.storage import IncidentStore


def test_list_returns_metadata_not_filesystem_paths(tmp_path):
    store = IncidentStore(tmp_path)
    incident = IncidentMetadata.new("inc-1", "2026-09-02T00:00:00Z", 40.0, 15.0)
    incident.state = IncidentState.ANALYSIS_FAILED
    incident.failure_reason = "model timeout"
    store.save(incident)

    response = TestClient(create_app(store)).get("/api/incidents")

    assert response.status_code == 200
    assert response.json() == [
        {
            "incident_id": "inc-1",
            "triggered_at": "2026-09-02T00:00:00Z",
            "state": "analysis_failed",
            "failure_reason": "model timeout",
            "has_clip": False,
            "has_report": False,
        }
    ]
    assert str(tmp_path) not in response.text


def test_list_excludes_incidents_still_being_processed(tmp_path):
    store = IncidentStore(tmp_path)
    states = [
        IncidentState.COLLECTING_POST_TRIGGER,
        IncidentState.CLIPPING,
        IncidentState.ANALYZING,
        IncidentState.READY,
        IncidentState.CLIP_FAILED,
        IncidentState.ANALYSIS_FAILED,
    ]
    for index, state in enumerate(states):
        incident = IncidentMetadata.new(
            f"inc-{index}", f"2026-09-02T00:00:0{index}Z", 40.0, 15.0
        )
        incident.state = state
        store.save(incident)

    assert [item.state for item in store.list()] == [
        IncidentState.ANALYSIS_FAILED,
        IncidentState.CLIP_FAILED,
        IncidentState.READY,
    ]

    response = TestClient(create_app(store)).get("/api/incidents")

    assert [item["state"] for item in response.json()] == [
        "analysis_failed",
        "clip_failed",
        "ready",
    ]
