from fastapi import FastAPI, Header, HTTPException

from dashpi.models import FileArtifact, IncidentState
from dashpi.ranges import range_response
from dashpi.storage import IncidentStore, sha256_file


def _is_valid_clip(clip: FileArtifact) -> bool:
    try:
        return (
            clip.path.is_file()
            and clip.byte_length > 0
            and clip.path.stat().st_size == clip.byte_length
            and sha256_file(clip.path) == clip.sha256
        )
    except OSError:
        return False


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
        except (FileNotFoundError, KeyError):
            raise HTTPException(404) from None
        if (
            item.state not in {IncidentState.READY, IncidentState.ANALYSIS_FAILED}
            or item.clip is None
            or not _is_valid_clip(item.clip)
        ):
            raise HTTPException(409)
        return range_response(item.clip.path, range_header, "video/mp4", item.clip.sha256)

    return app
