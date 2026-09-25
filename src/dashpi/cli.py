import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from dashpi.ai_client import load_ai_config
from dashpi.analysis import FAKE_MODEL, build_analyzer
from dashpi.config import OverlaySettings, Settings
from dashpi.media import segment_source
from dashpi.models import IncidentMetadata
from dashpi.pipeline import IncidentPipeline
from dashpi.storage import IncidentStore
from dashpi.vision import YoloDetector


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    simulate = subcommands.add_parser("simulate")
    simulate.add_argument("video", type=Path)
    simulate.add_argument("--trigger-seconds", type=float, required=True)
    simulate.add_argument("--data-root", type=Path, required=True)
    simulate.add_argument("--ai-model", default="x-ai/grok-4.7")
    simulate.add_argument("--ai-report-model", default="x-ai/grok-4.20")
    simulate.add_argument("--detector-model", type=Path)
    simulate.add_argument("--detection-confidence", type=float, default=0.45)
    simulate.add_argument("--show-traffic-lights", action="store_true")
    simulate.add_argument("--show-lanes", action="store_true")
    simulate.add_argument("--show-traffic-signs", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = Settings(
        args.data_root,
        args.ai_model,
        args.ai_report_model,
        detector_model=args.detector_model,
        detection_confidence=args.detection_confidence,
        overlays=OverlaySettings(
            args.show_traffic_lights,
            args.show_lanes,
            args.show_traffic_signs,
        ),
    )
    if settings.ai_model != FAKE_MODEL:
        load_ai_config()  # fail before creating media artifacts when no key is configured
    analyzer = build_analyzer(settings.ai_model, settings.ai_report_model, settings.data_root)
    segments = segment_source(args.video, settings.data_root / "raw", settings.segment_seconds)
    incident = IncidentMetadata.new(
        uuid.uuid4().hex,
        datetime.now(UTC).isoformat(),
        args.trigger_seconds,
        settings.post_seconds,
        settings.pre_seconds,
    )
    detector = (
        YoloDetector(settings.detector_model, settings.detection_confidence)
        if settings.detector_model
        else None
    )
    result = IncidentPipeline(settings, IncidentStore(settings.data_root), detector).process(
        incident, segments, analyzer
    )
    print(json.dumps(result.to_dict(), default=str))
