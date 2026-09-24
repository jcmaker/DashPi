"""Analyze a manually marked moment in an existing Pi video."""

from __future__ import annotations

from datetime import UTC, datetime
import math
from pathlib import Path
import uuid

from dashpi.config import Settings
from dashpi.media import probe_duration
from dashpi.models import IncidentMetadata, Segment
from dashpi.pipeline import IncidentPipeline
from dashpi.storage import IncidentStore


def analyze_external_video(source: Path, position: float, settings: Settings,
                           store: IncidentStore, analyze) -> IncidentMetadata:
    if not source.is_file():
        raise FileNotFoundError(f"영상을 찾을 수 없습니다: {source}")
    duration = probe_duration(source)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("재생 가능한 영상 길이를 확인할 수 없습니다.")
    if not math.isfinite(position) or position < 0:
        raise ValueError("사고 시점이 올바르지 않습니다.")
    position = min(position, duration)
    before = min(settings.pre_seconds, position)
    after = min(settings.post_seconds, duration - position)
    incident = IncidentMetadata.new(
        uuid.uuid4().hex, datetime.now(UTC).isoformat(), position, after, before,
    )
    return IncidentPipeline(settings, store).process(
        incident, [Segment(source, 0.0, duration)], analyze,
        incident_offset_override=before,
    )
