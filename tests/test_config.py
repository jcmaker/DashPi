from pathlib import Path

import pytest

from dashpi.config import Settings


def test_settings_use_approved_defaults(tmp_path: Path):
    settings = Settings(data_root=tmp_path, ollama_model="moondream")
    assert (settings.segment_seconds, settings.pre_seconds, settings.post_seconds) == (2.0, 30.0, 15.0)
    assert settings.frame_sample_count == 12


def test_model_name_is_required(tmp_path: Path):
    with pytest.raises(ValueError, match="ollama_model"):
        Settings(data_root=tmp_path, ollama_model="")
