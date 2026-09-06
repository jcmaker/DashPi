from fastapi.testclient import TestClient
from pathlib import Path

from dashpi.api import create_app
from dashpi.storage import IncidentStore


WEB_ROOT = Path(__file__).parents[1] / "src" / "dashpi" / "web"


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


def test_local_ui_offers_manual_report_controls_and_only_available_optical_transfer(tmp_path):
    response = TestClient(create_app(IncidentStore(tmp_path))).get("/")

    assert 'type="checkbox" name="traffic_lights"' in response.text
    assert 'type="number" name="incident_offset_seconds"' in response.text
    assert "리포트 다시 만들기" in response.text
    assert "정차 후 휴대폰으로 보내기" in response.text
    assert "optical_report_available" in response.text


def test_report_iframes_allow_only_offline_report_controls():
    for name in ("index.html", "receiver.html"):
        text = (WEB_ROOT / name).read_text()
        assert 'sandbox="allow-scripts allow-downloads allow-modals"' in text
        assert "allow-same-origin" not in text
