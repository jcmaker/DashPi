import sys
import json
from pathlib import Path

import pytest

from dashpi.cli import build_parser, main
from tests.media_factory import make_video


def test_cli_accepts_detector_and_independent_overlay_flags(tmp_path):
    args = build_parser().parse_args([
        "simulate", "input.mp4", "--trigger-seconds", "40",
        "--data-root", str(tmp_path), "--ai-model", "m",
        "--detector-model", "yolov8n.onnx", "--show-traffic-lights",
        "--show-traffic-signs",
    ])

    assert args.detector_model == Path("yolov8n.onnx")
    assert args.show_traffic_lights is True
    assert args.show_lanes is False
    assert args.show_traffic_signs is True


def test_cli_stops_before_media_work_when_the_api_key_is_missing(tmp_path, monkeypatch):
    from dashpi.ai_client import RetryableAnalysisError

    video = make_video(tmp_path / "source.mp4", 2)
    data_root = tmp_path / "data"
    monkeypatch.setattr("dashpi.cli.load_ai_config", lambda *_: (_ for _ in ()).throw(RetryableAnalysisError("API 키 없음")))
    monkeypatch.setattr(sys, "argv", ["dashpi", "simulate", str(video), "--trigger-seconds", "1",
                                      "--data-root", str(data_root)])

    with pytest.raises(RetryableAnalysisError, match="API 키 없음"):
        main()
    assert not data_root.exists()


def test_cli_fake_model_runs_offline_and_records_window(tmp_path, monkeypatch, capsys):
    video = make_video(tmp_path / "source.mp4", 6)
    from dashpi.config import Settings

    settings = Settings(tmp_path / "data", "fake", pre_seconds=2.0, post_seconds=2.0)
    monkeypatch.setattr("dashpi.cli.Settings", lambda *_args, **_kwargs: settings)
    monkeypatch.setattr(sys, "argv", ["dashpi", "simulate", str(video), "--trigger-seconds", "3",
                                      "--data-root", str(tmp_path / "data"), "--ai-model", "fake"])

    main()

    output = json.loads(capsys.readouterr().out)
    assert (output["pre_seconds"], output["post_seconds"], output["state"]) == (2.0, 2.0, "ready")
