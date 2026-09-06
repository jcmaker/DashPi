from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class OverlaySettings:
    traffic_lights: bool = False
    lanes: bool = False
    traffic_signs: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "traffic_lights": self.traffic_lights,
            "lanes": self.lanes,
            "traffic_signs": self.traffic_signs,
        }


@dataclass(frozen=True)
class Settings:
    data_root: Path
    ollama_model: str
    segment_seconds: float = 2.0
    pre_seconds: float = 30.0
    post_seconds: float = 15.0
    frame_sample_count: int = 12
    raw_max_fraction: float = 0.70
    min_free_fraction: float = 0.10
    detector_model: Path | None = None
    detection_confidence: float = 0.45
    overlays: OverlaySettings = field(default_factory=OverlaySettings)

    def __post_init__(self) -> None:
        if not self.ollama_model.strip():
            raise ValueError("ollama_model is required")
        if min(self.segment_seconds, self.pre_seconds, self.post_seconds) <= 0:
            raise ValueError("recording durations must be positive")
        if not 0.0 < self.detection_confidence <= 1.0:
            raise ValueError("detection_confidence must be in (0, 1]")
