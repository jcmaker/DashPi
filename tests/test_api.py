import hashlib
import json
import shutil
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
import threading

import pytest
from fastapi.testclient import TestClient

import dashpi.api as api_module
import dashpi.ranges as ranges_module
import dashpi.storage as storage_module
from dashpi.api import create_app
from dashpi.config import OverlaySettings
from dashpi.models import FileArtifact, IncidentMetadata, IncidentState
from dashpi.optical.container import MAX_PAYLOAD, unpack_container
from dashpi.optical.protocol import parse_frame
from dashpi.optical.session import OpticalSession
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
    return TestClient(create_app(store)), payload, incident.clip, store


def ready_store_with_clip(tmp_path, duration):
    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("inc-1", "2026-09-06T00:00:00Z", 40.0, 15.0)
    item.state = IncidentState.READY
    item.clip = replace(atomic_write(store.directory("inc-1") / "clip.mp4", b"clip"), duration=duration)
    item.report_json = atomic_write(store.directory("inc-1") / "report.json", b'{"summary":"old"}')
    item.report_html = atomic_write(store.directory("inc-1") / "report.html", b"<h1>old</h1>")
    store.save(item)
    return store, item


def test_list_reports_optical_availability_from_verified_html_size(client_with_ready_incident):
    client, _payload, _clip, _store = client_with_ready_incident

    item = client.get("/api/incidents").json()[0]

    assert item["optical_report_available"] is True
    assert item["clip_duration"] is None


def test_report_regeneration_passes_manual_time_and_overlay_settings(tmp_path):
    store, item = ready_store_with_clip(tmp_path, duration=45.0)
    calls = []

    def regenerate(incident, offset, overlays):
        calls.append((incident.incident_id, offset, overlays))
        return incident

    client = TestClient(create_app(store, regenerate_report=regenerate))
    assert client.get("/api/incidents").json()[0]["clip_duration"] == 45.0

    response = client.post("/api/incidents/inc-1/report", json={
        "incident_offset_seconds": 4.0,
        "traffic_lights": True,
        "lanes": False,
        "traffic_signs": True,
    })

    assert response.status_code == 200
    assert response.json() == {"state": "ready"}
    assert calls == [("inc-1", 4.0, OverlaySettings(True, False, True))]


def test_report_regeneration_rejects_time_outside_evidence(tmp_path):
    store, _item = ready_store_with_clip(tmp_path, duration=45.0)
    client = TestClient(create_app(store, regenerate_report=lambda *_: pytest.fail()))

    assert client.post("/api/incidents/inc-1/report", json={"incident_offset_seconds": 46.0}).status_code == 422


def test_report_regeneration_returns_analyzing_when_worker_queues_report(tmp_path):
    store, _item = ready_store_with_clip(tmp_path, duration=45.0)
    queued = Future()

    response = TestClient(create_app(store, regenerate_report=lambda *_: queued)).post(
        "/api/incidents/inc-1/report", json={}
    )

    assert response.status_code == 202
    assert response.json() == {"state": "analyzing"}


@pytest.fixture
def client_with_oversized_incident(tmp_path):
    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("inc-big", "2026-09-02T00:00:00Z", 40.0, 15.0)
    item.state = IncidentState.READY
    item.clip = atomic_write(store.directory("inc-big") / "clip.mp4", b"x" * (MAX_PAYLOAD + 1))
    store.save(item)
    return TestClient(create_app(store))


def test_api_refuses_oversized_clip(client_with_oversized_incident):
    response = client_with_oversized_incident.post(
        "/api/incidents/inc-big/optical", json={"artifact": "clip", "block_size": 512}
    )

    assert response.status_code == 413


def test_api_refuses_verified_clip_larger_than_bounded_reread(tmp_path):
    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("inc-bigger", "2026-09-02T00:00:00Z", 40.0, 15.0)
    item.state = IncidentState.READY
    item.clip = atomic_write(
        store.directory("inc-bigger") / "clip.mp4", b"x" * (MAX_PAYLOAD + 4096)
    )
    store.save(item)

    response = TestClient(create_app(store)).post(
        "/api/incidents/inc-bigger/optical", json={"artifact": "clip", "block_size": 512}
    )

    assert response.status_code == 413


def test_optical_frame_is_binary_no_store_and_latest_session_replaces_prior(
    client_with_ready_incident,
):
    client, _payload, _clip, _store = client_with_ready_incident

    first = client.post(
        "/api/incidents/inc-1/optical", json={"artifact": "report", "block_size": 512}
    )
    second = client.post(
        "/api/incidents/inc-1/optical", json={"artifact": "clip", "block_size": 512}
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert client.get(f"/api/optical/{first.json()['session_id']}").status_code == 404
    status = client.get(f"/api/optical/{second.json()['session_id']}")
    frame = client.get(f"/api/optical/{second.json()['session_id']}/frames/0")
    assert status.json() == second.json()
    assert frame.headers["content-type"].startswith("application/octet-stream")
    assert frame.headers["cache-control"] == "no-store"
    assert parse_frame(frame.content).session_id == second.json()["session_id"]


def test_optical_clip_allows_analysis_failure_but_report_requires_ready(client_with_ready_incident):
    client, _payload, _clip, store = client_with_ready_incident
    incident = store.load("inc-1")
    incident.state = IncidentState.ANALYSIS_FAILED
    store.save(incident)

    clip = client.post(
        "/api/incidents/inc-1/optical", json={"artifact": "clip", "block_size": 512}
    )
    report = client.post(
        "/api/incidents/inc-1/optical", json={"artifact": "report", "block_size": 512}
    )

    assert clip.status_code == 200
    assert report.status_code == 409


@pytest.mark.parametrize("damage", ["integrity", "symlink"])
def test_optical_rejects_unverified_clip_artifact(client_with_ready_incident, tmp_path, damage):
    client, _payload, clip, _store = client_with_ready_incident
    if damage == "integrity":
        clip.path.write_bytes(b"tampered")
    else:
        target = atomic_write(tmp_path / "outside.mp4", clip.path.read_bytes())
        clip.path.unlink()
        clip.path.symlink_to(target.path)

    response = client.post(
        "/api/incidents/inc-1/optical", json={"artifact": "clip", "block_size": 512}
    )

    assert response.status_code == 409


def test_optical_uses_verified_descriptor_when_artifact_path_is_replaced(
    client_with_ready_incident, monkeypatch
):
    client, payload, clip, _store = client_with_ready_incident

    def replace_after_hash(source):
        digest = hashlib.sha256()
        source.seek(0)
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
        atomic_write(clip.path, b"x" * len(payload))
        return digest.hexdigest()

    monkeypatch.setattr(ranges_module, "_sha256_descriptor", replace_after_hash)

    started = client.post(
        "/api/incidents/inc-1/optical", json={"artifact": "clip", "block_size": 512}
    )

    assert started.status_code == 200
    frame = client.get(f"/api/optical/{started.json()['session_id']}/frames/0")
    parsed = parse_frame(frame.content)
    assert unpack_container(parsed.symbol[: parsed.total_length]).payload == payload


def test_optical_does_not_reopen_metadata_artifact_path(client_with_ready_incident, monkeypatch):
    client, _payload, _clip, _store = client_with_ready_incident

    def fail_if_reopened(_path):
        raise AssertionError("optical endpoint reopened the metadata path")

    monkeypatch.setattr(type(_clip.path), "read_bytes", fail_if_reopened)

    response = client.post(
        "/api/incidents/inc-1/optical", json={"artifact": "clip", "block_size": 512}
    )

    assert response.status_code == 200


@pytest.mark.parametrize("value", [-1, 2**32])
def test_optical_rejects_frame_identifiers_outside_protocol_domain(
    client_with_ready_incident, value
):
    client, _payload, _clip, _store = client_with_ready_incident
    started = client.post(
        "/api/incidents/inc-1/optical", json={"artifact": "clip", "block_size": 512}
    )
    session_id = started.json()["session_id"]

    assert client.get(f"/api/optical/{value}").status_code == 404
    assert client.get(f"/api/optical/{session_id}/frames/{value}").status_code == 404


def test_latest_optical_session_slot_keeps_one_current_session_under_concurrent_starts():
    current = api_module.LatestOpticalSession()
    first = OpticalSession.from_bytes("one.html", b"one", "text/html", 512, 1)
    second = OpticalSession.from_bytes("two.html", b"two", "text/html", 512, 2)
    start = threading.Barrier(3)

    def replace(session):
        start.wait()
        current.replace(session)

    with ThreadPoolExecutor(max_workers=2) as workers:
        first_write = workers.submit(replace, first)
        second_write = workers.submit(replace, second)
        start.wait()
        first_write.result()
        second_write.result()

    assert sum(current.get(session_id) is not None for session_id in (1, 2)) == 1


def test_existing_malformed_metadata_is_a_conflict_not_not_found(client_with_ready_incident):
    client, _payload, _clip, store = client_with_ready_incident
    (store.directory("inc-1") / "metadata.json").write_text('{"incident_id":"inc-1"}')

    assert client.get("/api/incidents/inc-1/clip").status_code == 409
    assert (
        client.post(
            "/api/incidents/inc-1/optical", json={"artifact": "clip", "block_size": 512}
        ).status_code
        == 409
    )


@pytest.mark.parametrize("change", ["mutate", "grow"])
def test_optical_rechecks_exact_verified_bytes_after_in_place_artifact_change(
    client_with_ready_incident, monkeypatch, change
):
    client, payload, clip, _store = client_with_ready_incident

    def hash_then_change(source):
        digest = hashlib.sha256()
        source.seek(0)
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
        with clip.path.open("r+b") as target:
            if change == "mutate":
                target.write(b"x" * len(payload))
            else:
                target.seek(0, 2)
                target.write(b"x")
        return digest.hexdigest()

    monkeypatch.setattr(ranges_module, "_sha256_descriptor", hash_then_change)

    response = client.post(
        "/api/incidents/inc-1/optical", json={"artifact": "clip", "block_size": 512}
    )

    assert response.status_code == 409


def test_clip_supports_resume_and_hash(client_with_ready_incident):
    client, payload, clip, _store = client_with_ready_incident

    response = client.get("/api/incidents/inc-1/clip", headers={"Range": "bytes=4-8"})

    assert response.status_code == 206
    assert response.content == payload[4:9]
    assert response.headers["content-range"] == f"bytes 4-8/{len(payload)}"
    assert response.headers["etag"] == f'"sha256:{clip.sha256}"'


def test_invalid_incident_id_does_not_escape_store(client_with_ready_incident):
    client, _payload, _clip, _store = client_with_ready_incident

    assert client.get("/api/incidents/invalid!/clip").status_code == 404


@pytest.mark.parametrize("damage", ["missing", "zero_length", "size_mismatch", "digest_mismatch"])
@pytest.mark.parametrize("headers", [{}, {"Range": "bytes=4-8"}])
def test_clip_with_invalid_artifact_is_not_exposed(client_with_ready_incident, damage, headers):
    client, _payload, clip, _store = client_with_ready_incident
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


def test_clip_rejects_metadata_path_outside_incident(client_with_ready_incident, tmp_path):
    client, payload, _clip, store = client_with_ready_incident
    incident = store.load("inc-1")
    incident.clip = atomic_write(tmp_path / "outside.mp4", payload)
    store.save(incident)

    response = client.get("/api/incidents/inc-1/clip")

    assert response.status_code == 409
    assert "etag" not in response.headers


def test_clip_rejects_symlink_even_when_target_matches_metadata(client_with_ready_incident, tmp_path):
    client, payload, clip, _store = client_with_ready_incident
    target = atomic_write(tmp_path / "outside.mp4", payload)
    clip.path.unlink()
    clip.path.symlink_to(target.path)

    response = client.get("/api/incidents/inc-1/clip")

    assert response.status_code == 409
    assert "etag" not in response.headers


def test_clip_rejects_malformed_digest_metadata(client_with_ready_incident):
    client, _payload, clip, store = client_with_ready_incident
    incident = store.load("inc-1")
    incident.clip = FileArtifact(clip.path, clip.byte_length, None)  # type: ignore[arg-type]
    store.save(incident)

    response = client.get("/api/incidents/inc-1/clip")

    assert response.status_code == 409
    assert "etag" not in response.headers


def test_clip_streams_opened_descriptor_after_path_replacement(
    client_with_ready_incident, monkeypatch
):
    client, payload, clip, _store = client_with_ready_incident
    replacement = b"x" * len(payload)

    def replace_after_descriptor_hash(source):
        digest = hashlib.sha256()
        source.seek(0)
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
        atomic_write(clip.path, replacement)
        return digest.hexdigest()

    monkeypatch.setattr(ranges_module, "_sha256_descriptor", replace_after_descriptor_hash)

    response = client.get("/api/incidents/inc-1/clip", headers={"Range": "bytes=4-8"})

    assert response.status_code == 206
    assert response.content == payload[4:9]
    assert response.headers["etag"] == f'"sha256:{clip.sha256}"'


@pytest.mark.parametrize(
    "path",
    ["/api/incidents/inc-1", "/api/incidents/inc-1/report.html", "/api/incidents/inc-1/clip"],
)
def test_artifact_routes_reject_symlinked_incident_directory(
    client_with_ready_incident, tmp_path, path
):
    client, _payload, _clip, store = client_with_ready_incident
    incident_directory = store.directory("inc-1")
    outside_directory = tmp_path / "outside-incident"
    incident_directory.replace(outside_directory)
    incident_directory.symlink_to(outside_directory, target_is_directory=True)

    response = client.get(path)

    assert response.status_code == 409
    assert "etag" not in response.headers


def test_clip_keeps_open_incident_directory_after_directory_replacement(
    client_with_ready_incident, tmp_path, monkeypatch
):
    client, payload, clip, store = client_with_ready_incident
    incident_directory = store.directory("inc-1")
    replacement_directory = tmp_path / "replacement-incident"
    retired_directory = tmp_path / "retired-incident"
    shutil.copytree(incident_directory, replacement_directory)
    (replacement_directory / "clip.mp4").write_bytes(b"x" * len(payload))
    real_loads = storage_module.json.loads
    replaced = False

    def replace_directory_after_metadata_parse(value, *args, **kwargs):
        nonlocal replaced
        metadata = real_loads(value, *args, **kwargs)
        if not replaced and isinstance(metadata, dict) and metadata.get("incident_id") == "inc-1":
            replaced = True
            incident_directory.replace(retired_directory)
            replacement_directory.replace(incident_directory)
        return metadata

    monkeypatch.setattr(storage_module.json, "loads", replace_directory_after_metadata_parse)

    response = client.get("/api/incidents/inc-1/clip", headers={"Range": "bytes=4-8"})

    assert response.status_code == 206
    assert response.content == payload[4:9]
    assert response.headers["etag"] == f'"sha256:{clip.sha256}"'


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
            "clip_duration": None,
            "optical_report_available": False,
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


def test_report_is_same_origin_html(client_with_ready_incident):
    client, _payload, _clip, _store = client_with_ready_incident

    response = client.get("/api/incidents/inc-1/report.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "DashPi incident report" in response.text


def test_incident_detail_returns_report_without_paths(client_with_ready_incident):
    client, _payload, _clip, store = client_with_ready_incident

    response = client.get("/api/incidents/inc-1")

    assert response.status_code == 200
    assert response.json()["report"]["summary"] == "Stopped"
    assert "report.html" not in response.text and "clip.mp4" not in response.text
    assert str(store.root) not in response.text


def test_report_detail_and_html_require_ready(client_with_ready_incident):
    client, _payload, _clip, store = client_with_ready_incident
    incident = store.load("inc-1")
    incident.state = IncidentState.ANALYSIS_FAILED
    store.save(incident)

    assert client.get("/api/incidents/inc-1").status_code == 409
    assert client.get("/api/incidents/inc-1/report.html").status_code == 409


@pytest.mark.parametrize("artifact_name", ["report_json", "report_html"])
@pytest.mark.parametrize("damage", ["outside", "symlink", "directory", "empty", "size", "digest"])
def test_report_artifacts_must_be_canonical_regular_and_intact(
    client_with_ready_incident, tmp_path, artifact_name, damage
):
    client, _payload, _clip, store = client_with_ready_incident
    incident = store.load("inc-1")
    artifact = getattr(incident, artifact_name)
    assert artifact is not None
    if damage == "outside":
        suffix = "json" if artifact_name == "report_json" else "html"
        replacement = atomic_write(tmp_path / f"outside.{suffix}", artifact.path.read_bytes())
        setattr(incident, artifact_name, replacement)
        store.save(incident)
    elif damage == "symlink":
        target = atomic_write(tmp_path / artifact.path.name, artifact.path.read_bytes())
        artifact.path.unlink()
        artifact.path.symlink_to(target.path)
    elif damage == "directory":
        artifact.path.unlink()
        artifact.path.mkdir()
    elif damage == "empty":
        artifact.path.write_bytes(b"")
    elif damage == "size":
        artifact.path.write_bytes(b"too short")
    else:
        artifact.path.write_bytes(b"x" * artifact.byte_length)

    assert client.get("/api/incidents/inc-1").status_code == 409
    assert client.get("/api/incidents/inc-1/report.html").status_code == 409


def test_report_rejects_malformed_json(client_with_ready_incident):
    client, _payload, _clip, store = client_with_ready_incident
    incident = store.load("inc-1")
    incident.report_json = atomic_write(
        store.directory("inc-1") / "report.json", b"not valid JSON"
    )
    store.save(incident)

    assert client.get("/api/incidents/inc-1").status_code == 409
    assert client.get("/api/incidents/inc-1/report.html").status_code == 409


def test_metadata_incident_id_must_match_route_before_artifact_resolution(
    client_with_ready_incident,
):
    client, _payload, _clip, store = client_with_ready_incident
    metadata_path = store.directory("inc-1") / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["incident_id"] = "inc-2"
    metadata_path.write_text(json.dumps(metadata))

    assert client.get("/api/incidents/inc-1").status_code == 409
    assert client.get("/api/incidents/inc-1/report.html").status_code == 409
    assert client.get("/api/incidents/inc-1/clip").status_code == 409


@pytest.mark.parametrize(
    "path",
    ["/api/incidents/inc-1", "/api/incidents/inc-1/report.html", "/api/incidents/inc-1/clip"],
)
def test_artifact_routes_use_only_the_store_resolved_directory(
    client_with_ready_incident, path
):
    _client, _payload, _clip, store = client_with_ready_incident

    class OneResolutionStore(IncidentStore):
        def __init__(self, root):
            super().__init__(root)
            self.resolutions = 0

        def directory(self, incident_id):
            self.resolutions += 1
            if self.resolutions > 1:
                raise AssertionError("API recomputed an incident directory")
            return super().directory(incident_id)

    client = TestClient(create_app(OneResolutionStore(store.root)), raise_server_exceptions=False)

    assert client.get(path).status_code == 200
