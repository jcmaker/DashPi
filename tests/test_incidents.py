from pathlib import Path

from dashpi.config import Settings
from dashpi.incidents import IncidentCoordinator, segments_for_window
from dashpi.models import IncidentState, Segment


def test_window_selects_every_overlapping_segment(tmp_path: Path):
    segments = [Segment(tmp_path / f"{n}.mp4", n, n + 2) for n in range(0, 60, 2)]
    selected = segments_for_window(segments, start=10.0, end=25.0)
    assert (selected[0].start_mono, selected[-1].end_mono) == (10, 26)


def test_window_excludes_segments_touching_boundary(tmp_path: Path):
    segments = [
        Segment(tmp_path / "before.mp4", 0, 10),
        Segment(tmp_path / "inside.mp4", 10, 12),
        Segment(tmp_path / "after.mp4", 12, 14),
    ]
    assert segments_for_window(segments, start=10.0, end=12.0) == [segments[1]]


def test_overlapping_trigger_extends_existing_incident(tmp_path: Path):
    coordinator = IncidentCoordinator(Settings(tmp_path, "moondream"), id_factory=iter(["inc-1", "inc-2"]).__next__)
    first = coordinator.trigger(40.0, "2026-09-02T00:00:00Z")
    second = coordinator.trigger(50.0, "2026-09-02T00:00:10Z")
    assert second.incident_id == first.incident_id
    assert second.post_deadline_mono == 65.0


def test_ready_at_returns_due_collecting_incidents(tmp_path: Path):
    coordinator = IncidentCoordinator(Settings(tmp_path, "moondream"), id_factory=iter(["inc-1", "inc-2"]).__next__)
    due = coordinator.trigger(40.0, "2026-09-02T00:00:00Z")
    later = coordinator.trigger(100.0, "2026-09-02T00:01:00Z")
    later.transition(IncidentState.READY, "2026-09-02T00:02:00Z")
    assert coordinator.ready_at(55.0) == [due]


def test_overlapping_trigger_after_terminal_incident_creates_new_incident(tmp_path: Path):
    coordinator = IncidentCoordinator(Settings(tmp_path, "moondream"), id_factory=iter(["inc-1", "inc-2"]).__next__)
    first = coordinator.trigger(40.0, "2026-09-02T00:00:00Z")
    first.transition(IncidentState.READY, "2026-09-02T00:01:00Z")

    second = coordinator.trigger(50.0, "2026-09-02T00:01:10Z")

    assert second.incident_id == "inc-2"
    assert second.state is IncidentState.COLLECTING_POST_TRIGGER


def test_coordinator_records_configured_incident_window_durations(tmp_path: Path):
    coordinator = IncidentCoordinator(
        Settings(tmp_path, "moondream", pre_seconds=12.0, post_seconds=7.0), id_factory=lambda: "inc-1"
    )

    incident = coordinator.trigger(40.0, "2026-09-02T00:00:00Z")

    assert (incident.pre_seconds, incident.post_seconds) == (12.0, 7.0)
