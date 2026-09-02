import hashlib
import socket

from fastapi.testclient import TestClient

from dashpi.api import create_app
from dashpi.models import IncidentMetadata, IncidentState
from dashpi.storage import IncidentStore, atomic_write


def test_local_routes_rebuild_clip_without_outbound_network(tmp_path, monkeypatch):
    def blocked(*_args, **_kwargs):
        raise AssertionError("outbound network attempted")

    monkeypatch.setattr(socket, "create_connection", blocked)
    payload = bytes(range(256)) * 8
    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("inc-1", "2026-09-02T00:00:00Z", 40.0, 15.0)
    item.state = IncidentState.READY
    item.clip = atomic_write(store.directory("inc-1") / "clip.mp4", payload)
    item.report_html = atomic_write(
        store.directory("inc-1") / "report.html", b"<h1>DashPi incident report</h1>"
    )
    store.save(item)
    client = TestClient(create_app(store))

    assert client.get("/").status_code == 200
    assert client.get("/api/incidents").json()[0]["incident_id"] == "inc-1"
    first = client.get("/api/incidents/inc-1/clip", headers={"Range": "bytes=0-1023"}).content
    second = client.get("/api/incidents/inc-1/clip", headers={"Range": "bytes=1024-"}).content
    assert hashlib.sha256(first + second).hexdigest() == item.clip.sha256
