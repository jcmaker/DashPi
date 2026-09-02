from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path


class IncidentState(StrEnum):
    COLLECTING_POST_TRIGGER = "collecting_post_trigger"
    CLIPPING = "clipping"
    ANALYZING = "analyzing"
    READY = "ready"
    CLIP_FAILED = "clip_failed"
    ANALYSIS_FAILED = "analysis_failed"


@dataclass(frozen=True)
class Segment:
    path: Path
    start_mono: float
    end_mono: float


@dataclass(frozen=True)
class FileArtifact:
    path: Path
    byte_length: int
    sha256: str


@dataclass
class IncidentMetadata:
    incident_id: str
    triggered_at: str
    trigger_mono: float
    post_deadline_mono: float
    state: IncidentState
    failure_reason: str | None = None
    clip: FileArtifact | None = None
    report_json: FileArtifact | None = None
    report_html: FileArtifact | None = None
    transitions: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def new(cls, incident_id: str, wall_time: str, trigger_mono: float, post_seconds: float) -> "IncidentMetadata":
        item = cls(incident_id, wall_time, trigger_mono, trigger_mono + post_seconds, IncidentState.COLLECTING_POST_TRIGGER)
        item.transitions.append({"state": item.state.value, "at": wall_time})
        return item

    def transition(self, state: IncidentState, at: str, failure_reason: str | None = None) -> None:
        self.state, self.failure_reason = state, failure_reason
        self.transitions.append({"state": state.value, "at": at})

    def to_dict(self) -> dict:
        return asdict(self)
