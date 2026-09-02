import json
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles

from dashpi.models import IncidentState
from dashpi.ranges import _open_verified_file, range_response
from dashpi.storage import IncidentStore


def create_app(store: IncidentStore) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None)

    @app.get("/api/incidents")
    def list_incidents():
        return [
            {
                "incident_id": item.incident_id,
                "triggered_at": item.triggered_at,
                "state": item.state,
                "failure_reason": item.failure_reason,
                "has_clip": item.state in {IncidentState.READY, IncidentState.ANALYSIS_FAILED}
                and item.clip is not None,
                "has_report": item.state is IncidentState.READY
                and item.report_json is not None
                and item.report_html is not None,
            }
            for item in store.list()
        ]

    def load_report(incident_id: str):
        try:
            item = store.load(incident_id)
        except (FileNotFoundError, KeyError):
            raise HTTPException(404) from None
        if item.incident_id != incident_id:
            raise HTTPException(409)
        if item.state is not IncidentState.READY:
            raise HTTPException(409)
        if item.report_json is None or item.report_html is None:
            raise HTTPException(404)
        directory = store.directory(item.incident_id)
        if (
            item.report_json.path != directory / "report.json"
            or item.report_html.path != directory / "report.html"
        ):
            raise HTTPException(409)
        report_source, _ = _open_verified_file(
            item.report_json.path, item.report_json.byte_length, item.report_json.sha256
        )
        try:
            report_source.seek(0)
            report = json.loads(report_source.read())
        except (TypeError, ValueError, UnicodeDecodeError):
            raise HTTPException(409) from None
        finally:
            report_source.close()
        if not isinstance(report, dict):
            raise HTTPException(409)
        report_html_source, _ = _open_verified_file(
            item.report_html.path, item.report_html.byte_length, item.report_html.sha256
        )
        report_html_source.close()
        return item, report

    @app.get("/api/incidents/{incident_id}/report.html")
    def get_report(incident_id: str):
        item, _report = load_report(incident_id)
        assert item.report_html is not None
        return range_response(
            item.report_html.path,
            None,
            "text/html",
            item.report_html.sha256,
            item.report_html.byte_length,
        )

    @app.get("/api/incidents/{incident_id}")
    def get_incident(incident_id: str):
        item, report = load_report(incident_id)
        return {
            "incident_id": item.incident_id,
            "triggered_at": item.triggered_at,
            "state": item.state,
            "failure_reason": item.failure_reason,
            "report": report,
        }

    @app.get("/api/incidents/{incident_id}/clip")
    def get_clip(incident_id: str, range_header: str | None = Header(None, alias="Range")):
        try:
            item = store.load(incident_id)
        except (FileNotFoundError, KeyError):
            raise HTTPException(404) from None
        if item.incident_id != incident_id:
            raise HTTPException(409)
        clip_path = store.directory(item.incident_id) / "clip.mp4"
        if (
            item.state not in {IncidentState.READY, IncidentState.ANALYSIS_FAILED}
            or item.clip is None
            or item.clip.path != clip_path
        ):
            raise HTTPException(409)
        return range_response(
            clip_path,
            range_header,
            "video/mp4",
            item.clip.sha256,
            item.clip.byte_length,
        )

    app.mount("/", StaticFiles(directory=Path(__file__).parent / "web", html=True), name="web")

    return app
