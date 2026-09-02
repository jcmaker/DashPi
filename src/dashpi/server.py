import argparse
from pathlib import Path

import uvicorn

from dashpi.api import create_app
from dashpi.storage import IncidentStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    uvicorn.run(create_app(IncidentStore(args.data_root)), host=args.host, port=args.port)
