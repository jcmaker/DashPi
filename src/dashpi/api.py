from fastapi import FastAPI, Header, HTTPException

from dashpi.models import IncidentState
from dashpi.ranges import range_response
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
                "has_clip": item.clip is not None,
                "has_report": item.report_html is not None,
            }
            for item in store.list()
        ]

    @app.get("/api/incidents/{incident_id}/clip")
    def get_clip(incident_id: str, range_header: str | None = Header(None, alias="Range")):
        try:
            item = store.load(incident_id)
            clip_path = store.directory(incident_id) / "clip.mp4"
        except (FileNotFoundError, KeyError):
            raise HTTPException(404) from None
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

    return app
