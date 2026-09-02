from fastapi.testclient import TestClient

from dashpi.api import create_app
from dashpi.storage import IncidentStore


def test_local_ui_is_served_with_only_local_assets(tmp_path):
    response = TestClient(create_app(IncidentStore(tmp_path))).get("/")

    assert response.status_code == 200
    assert 'href="/tokens.css"' in response.text
    assert "https://" not in response.text and "http://" not in response.text


def test_local_ui_conditionally_embeds_incident_artifacts(tmp_path):
    response = TestClient(create_app(IncidentStore(tmp_path))).get("/")

    assert "item.has_report" in response.text
    assert "item.has_clip" in response.text
    assert '<iframe id="report" title="Incident report" sandbox' in response.text
    assert '<video controls preload="metadata"' in response.text
    assert "fetch('/api/incidents')" in response.text
