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
        report_html_source = None
        try:
            with store.open_incident(incident_id) as (item, directory_descriptor, directory):
                if item.incident_id != incident_id:
                    raise HTTPException(409)
                if item.state is not IncidentState.READY:
                    raise HTTPException(409)
                if item.report_json is None or item.report_html is None:
                    raise HTTPException(404)
                if (
                    item.report_json.path != directory / "report.json"
                    or item.report_html.path != directory / "report.html"
                ):
                    raise HTTPException(409)
                report_source, _ = _open_verified_file(
                    directory_descriptor,
                    "report.json",
                    item.report_json.byte_length,
                    item.report_json.sha256,
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
                report_html_source, report_html_size = _open_verified_file(
                    directory_descriptor,
                    "report.html",
                    item.report_html.byte_length,
                    item.report_html.sha256,
                )
        except (FileNotFoundError, KeyError):
            if report_html_source is not None:
                report_html_source.close()
            raise HTTPException(404) from None
        except (OSError, TypeError, ValueError, UnicodeDecodeError):
            if report_html_source is not None:
                report_html_source.close()
            raise HTTPException(409) from None
        return item, report, report_html_source, report_html_size

    @app.get("/api/incidents/{incident_id}/report.html")
    def get_report(incident_id: str):
        item, _report, report_html_source, report_html_size = load_report(incident_id)
        assert item.report_html is not None
        return range_response(
            report_html_source,
            report_html_size,
            None,
            "text/html",
            item.report_html.sha256,
        )

    @app.get("/api/incidents/{incident_id}")
    def get_incident(incident_id: str):
        item, report, report_html_source, _report_html_size = load_report(incident_id)
        try:
            return {
                "incident_id": item.incident_id,
                "triggered_at": item.triggered_at,
                "state": item.state,
                "failure_reason": item.failure_reason,
                "report": report,
            }
        finally:
            report_html_source.close()

    @app.get("/api/incidents/{incident_id}/clip")
    def get_clip(incident_id: str, range_header: str | None = Header(None, alias="Range")):
        clip_source = None
        try:
            with store.open_incident(incident_id) as (item, directory_descriptor, directory):
                if item.incident_id != incident_id:
                    raise HTTPException(409)
                clip_path = directory / "clip.mp4"
                if (
                    item.state not in {IncidentState.READY, IncidentState.ANALYSIS_FAILED}
                    or item.clip is None
                    or item.clip.path != clip_path
                ):
                    raise HTTPException(409)
                clip_source, clip_size = _open_verified_file(
                    directory_descriptor,
                    "clip.mp4",
                    item.clip.byte_length,
                    item.clip.sha256,
                )
        except (FileNotFoundError, KeyError):
            if clip_source is not None:
                clip_source.close()
            raise HTTPException(404) from None
        except (OSError, TypeError, ValueError, UnicodeDecodeError):
            if clip_source is not None:
                clip_source.close()
            raise HTTPException(409) from None
        return range_response(
            clip_source,
            clip_size,
            range_header,
            "video/mp4",
            item.clip.sha256,
        )

    app.mount("/", StaticFiles(directory=Path(__file__).parent / "web", html=True), name="web")

    return app
