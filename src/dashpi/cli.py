import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from dashpi.config import Settings
from dashpi.media import segment_source
from dashpi.models import IncidentMetadata
from dashpi.pipeline import IncidentPipeline
from dashpi.reports import OllamaClient
from dashpi.storage import IncidentStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    simulate = subcommands.add_parser("simulate")
    simulate.add_argument("video", type=Path)
    simulate.add_argument("--trigger-seconds", type=float, required=True)
    simulate.add_argument("--data-root", type=Path, required=True)
    simulate.add_argument("--ollama-model", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = Settings(args.data_root, args.ollama_model)
    segments = segment_source(args.video, settings.data_root / "raw", settings.segment_seconds)
    incident = IncidentMetadata.new(
        uuid.uuid4().hex,
        datetime.now(UTC).isoformat(),
        args.trigger_seconds,
        settings.post_seconds,
    )
    client = OllamaClient(settings.ollama_model)
    client.validate_model()
    result = IncidentPipeline(settings, IncidentStore(settings.data_root)).process(
        incident, segments, client.analyze
    )
    print(json.dumps(result.to_dict(), default=str))
