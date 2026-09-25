from pathlib import Path

import pytest

from dashpi.config import OverlaySettings, Settings


def test_settings_use_approved_defaults(tmp_path: Path):
    settings = Settings(data_root=tmp_path, ai_model="x-ai/grok-4.7")
    assert (settings.segment_seconds, settings.pre_seconds, settings.post_seconds) == (2.0, 30.0, 15.0)
    assert settings.frame_sample_count == 12
    assert settings.ai_report_model == "x-ai/grok-4.20"
    assert settings.report_model_label == "x-ai/grok-4.7 + x-ai/grok-4.20"


def test_model_names_are_required(tmp_path: Path):
    with pytest.raises(ValueError, match="ai_model"):
        Settings(data_root=tmp_path, ai_model="")
    with pytest.raises(ValueError, match="ai_report_model"):
        Settings(data_root=tmp_path, ai_model="m", ai_report_model=" ")


def test_fake_model_label_is_plain(tmp_path: Path):
    assert Settings(tmp_path, "fake").report_model_label == "fake"


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
