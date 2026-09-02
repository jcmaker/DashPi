import pytest
from fastapi.testclient import TestClient

from dashpi.api import create_app
from dashpi.models import IncidentMetadata, IncidentState
from dashpi.storage import IncidentStore, atomic_write


@pytest.fixture
def client_with_ready_incident(tmp_path):
    payload = bytes(range(32))
    store = IncidentStore(tmp_path)
    incident = IncidentMetadata.new("inc-1", "2026-09-02T00:00:00Z", 40.0, 15.0)
    incident.state = IncidentState.READY
    incident.clip = atomic_write(store.directory("inc-1") / "clip.mp4", payload)
    incident.report_json = atomic_write(
        store.directory("inc-1") / "report.json",
        b'{"summary":"Stopped","observations":[],"limitations":[]}',
    )
    incident.report_html = atomic_write(
        store.directory("inc-1") / "report.html", b"<h1>DashPi incident report</h1>"
    )
    store.save(incident)
    return TestClient(create_app(store)), payload, incident.clip


def test_clip_supports_resume_and_hash(client_with_ready_incident):
    client, payload, clip = client_with_ready_incident

    response = client.get("/api/incidents/inc-1/clip", headers={"Range": "bytes=4-8"})

    assert response.status_code == 206
    assert response.content == payload[4:9]
    assert response.headers["content-range"] == f"bytes 4-8/{len(payload)}"
    assert response.headers["etag"] == f'"sha256:{clip.sha256}"'


def test_invalid_incident_id_does_not_escape_store(client_with_ready_incident):
    client, _payload, _clip = client_with_ready_incident

    assert client.get("/api/incidents/invalid!/clip").status_code == 404


@pytest.mark.parametrize("damage", ["missing", "zero_length", "size_mismatch", "digest_mismatch"])
@pytest.mark.parametrize("headers", [{}, {"Range": "bytes=4-8"}])
def test_clip_with_invalid_artifact_is_not_exposed(client_with_ready_incident, damage, headers):
    client, _payload, clip = client_with_ready_incident
    if damage == "missing":
        clip.path.unlink()
    elif damage == "zero_length":
        clip.path.write_bytes(b"")
    elif damage == "size_mismatch":
        clip.path.write_bytes(b"too short")
    else:
        clip.path.write_bytes(b"x" * clip.byte_length)

    response = client.get("/api/incidents/inc-1/clip", headers=headers)

    assert response.status_code == 409
    assert "etag" not in response.headers


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
