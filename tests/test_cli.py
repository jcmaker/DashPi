import sys

import pytest

from dashpi.cli import main
from dashpi.reports import OllamaClient
from tests.media_factory import make_video


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
