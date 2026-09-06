from pathlib import Path

import pytest

from dashpi.config import OverlaySettings, Settings


def test_settings_use_approved_defaults(tmp_path: Path):
    settings = Settings(data_root=tmp_path, ollama_model="moondream")
    assert (settings.segment_seconds, settings.pre_seconds, settings.post_seconds) == (2.0, 30.0, 15.0)
    assert settings.frame_sample_count == 12


def test_model_name_is_required(tmp_path: Path):
    with pytest.raises(ValueError, match="ollama_model"):
        Settings(data_root=tmp_path, ollama_model="")


def test_optional_overlays_default_off_and_are_independent(tmp_path: Path):
    settings = Settings(tmp_path, "test-model")

    assert settings.overlays == OverlaySettings(False, False, False)
    assert settings.detector_model is None
    assert settings.detection_confidence == 0.45

    custom = OverlaySettings(traffic_lights=True, lanes=False, traffic_signs=True)
    assert custom.to_dict() == {
        "traffic_lights": True,
        "lanes": False,
        "traffic_signs": True,
    }


def test_detection_confidence_is_a_probability(tmp_path: Path):
    with pytest.raises(ValueError, match="detection_confidence"):
        Settings(tmp_path, "test-model", detection_confidence=1.1)
