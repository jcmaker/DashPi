import argparse
from pathlib import Path

import uvicorn

from dashpi.api import create_app
from dashpi.analysis_worker import AnalysisWorker
from dashpi.config import OverlaySettings, Settings
from dashpi.pipeline import IncidentPipeline
from dashpi.reports import OllamaClient
from dashpi.storage import IncidentStore
from dashpi.vision import YoloDetector


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ollama-model")
    parser.add_argument("--detector-model", type=Path)
    parser.add_argument("--show-traffic-lights", action="store_true")
    parser.add_argument("--show-lanes", action="store_true")
    parser.add_argument("--show-traffic-signs", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    store = IncidentStore(args.data_root)
    worker = None
    regenerate_report = None
    if args.ollama_model and args.detector_model:
        settings = Settings(
            args.data_root,
            args.ollama_model,
            detector_model=args.detector_model,
            overlays=OverlaySettings(
                args.show_traffic_lights,
                args.show_lanes,
                args.show_traffic_signs,
            ),
        )
        client = OllamaClient(settings.ollama_model)
        detector = YoloDetector(settings.detector_model, settings.detection_confidence)
        worker = AnalysisWorker()
        pipeline = IncidentPipeline(settings, store, detector, wait_for_capacity=worker.wait_for_capacity)

        def regenerate_report(item, offset, overlays):
            return worker.submit(
                lambda: pipeline.generate_report(item, client.analyze, offset, overlays)
            )

    app = create_app(store, regenerate_report=regenerate_report)
    if worker is not None:
        @app.on_event("shutdown")
        def close_worker():
            worker.close()

    uvicorn.run(app, host=args.host, port=args.port)
