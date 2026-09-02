from fastapi import FastAPI

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

    return app
