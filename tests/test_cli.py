import sys
import json
from pathlib import Path

import pytest

from dashpi.cli import build_parser, main
from dashpi.reports import OllamaClient
from tests.media_factory import make_video


def test_cli_accepts_detector_and_independent_overlay_flags(tmp_path):
    args = build_parser().parse_args([
        "simulate", "input.mp4", "--trigger-seconds", "40",
        "--data-root", str(tmp_path), "--ollama-model", "m",
        "--detector-model", "yolov8n.onnx", "--show-traffic-lights",
        "--show-traffic-signs",
    ])

    assert args.detector_model == Path("yolov8n.onnx")
    assert args.show_traffic_lights is True
    assert args.show_lanes is False
    assert args.show_traffic_signs is True


def test_cli_validates_model_before_creating_media_artifacts(tmp_path, monkeypatch):
    video = make_video(tmp_path / "source.mp4", 2)
    data_root = tmp_path / "data"

    def model_unavailable(_self):
        raise ValueError("Ollama model not installed: missing-model")

    monkeypatch.setattr(OllamaClient, "validate_model", model_unavailable)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dashpi",
            "simulate",
            str(video),
            "--trigger-seconds",
            "1",
            "--data-root",
            str(data_root),
            "--ollama-model",
            "missing-model",
        ],
    )

    with pytest.raises(ValueError, match="Ollama model not installed: missing-model"):
        main()

    assert not data_root.exists()


def test_cli_records_configured_window_durations_in_metadata(tmp_path, monkeypatch, capsys):
    video = make_video(tmp_path / "source.mp4", 6)
    data_root = tmp_path / "data"

    from dashpi.config import Settings

    settings = Settings(data_root, "test-model", pre_seconds=2.0, post_seconds=2.0)
    monkeypatch.setattr("dashpi.cli.Settings", lambda *_args, **_kwargs: settings)
    monkeypatch.setattr(OllamaClient, "validate_model", lambda _self: None)
    monkeypatch.setattr(
        OllamaClient,
        "analyze",
        lambda _self, _frames: {"summary": "Stopped", "observations": [], "limitations": []},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dashpi",
            "simulate",
            str(video),
            "--trigger-seconds",
            "3",
            "--data-root",
            str(data_root),
            "--ollama-model",
            "test-model",
        ],
    )

    main()

    output = json.loads(capsys.readouterr().out)
    assert (output["pre_seconds"], output["post_seconds"]) == (2.0, 2.0)
