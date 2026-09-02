from collections.abc import Callable

from dashpi.config import Settings
from dashpi.models import IncidentMetadata, IncidentState, Segment


def segments_for_window(segments: list[Segment], start: float, end: float) -> list[Segment]:
    return [segment for segment in segments if segment.start_mono < end and segment.end_mono > start]


class IncidentCoordinator:
    def __init__(self, settings: Settings, id_factory: Callable[[], str]):
        self.settings, self.id_factory, self.active = settings, id_factory, []

    def trigger(self, trigger_mono: float, wall_time: str) -> IncidentMetadata:
        requested_start = trigger_mono - self.settings.pre_seconds
        requested_end = trigger_mono + self.settings.post_seconds
        for incident in self.active:
            if incident.state is not IncidentState.COLLECTING_POST_TRIGGER:
                continue
            existing_start = incident.trigger_mono - self.settings.pre_seconds
            if existing_start < requested_end and incident.post_deadline_mono > requested_start:
                incident.post_deadline_mono = max(incident.post_deadline_mono, requested_end)
                return incident
        incident = IncidentMetadata.new(
            self.id_factory(),
            wall_time,
            trigger_mono,
            self.settings.post_seconds,
            self.settings.pre_seconds,
        )
        self.active.append(incident)
        return incident

    def ready_at(self, now: float) -> list[IncidentMetadata]:
        return [item for item in self.active if item.state is IncidentState.COLLECTING_POST_TRIGGER and item.post_deadline_mono <= now]
