from pathlib import Path

import pytest

from dashpi.models import FileArtifact, IncidentMetadata, IncidentState, Segment
from dashpi.storage import IncidentStore, atomic_write, bytes_to_free, choose_prunable_segments


def test_atomic_write_leaves_only_complete_file(tmp_path: Path):
    artifact = atomic_write(tmp_path / "report.json", b'{"ok":true}')
    assert artifact.path.read_bytes() == b'{"ok":true}'
    assert artifact.sha256 == "4062edaf750fb8074e7e83e0c9028c94e32468a8b6f1614774328ef045150f93"
    assert not (tmp_path / "report.json.partial").exists()


def test_store_round_trips_incident(tmp_path: Path):
    store = IncidentStore(tmp_path)
    incident = IncidentMetadata.new("inc-1", "2026-09-02T00:00:00Z", 40.0, 15.0, pre_seconds=30.0)
    incident.clip = atomic_write(store.directory("inc-1") / "clip.mp4", b"clip")
    incident.clip = FileArtifact(incident.clip.path, incident.clip.byte_length, incident.clip.sha256, 44.9)
    incident.report_json = atomic_write(store.directory("inc-1") / "report.json", b"{}")
    incident.report_html = atomic_write(store.directory("inc-1") / "report.html", b"<main></main>")
    incident.report_model = "moondream"
    incident.report_generated_at = "2026-09-02T00:01:00Z"
    incident.transition(IncidentState.CLIPPING, "2026-09-02T00:00:01Z")
    incident.transition(IncidentState.ANALYZING, "2026-09-02T00:00:02Z")
    incident.transition(IncidentState.READY, "2026-09-02T00:01:01Z")
    store.save(incident)

    loaded = store.load("inc-1")

    assert loaded.to_dict() == incident.to_dict()


def test_store_loads_metadata_written_before_window_fields(tmp_path: Path):
    store = IncidentStore(tmp_path)
    directory = store.directory("inc-1")
    directory.mkdir(parents=True)
    (directory / "metadata.json").write_text(
        '{"incident_id":"inc-1","triggered_at":"now","trigger_mono":40.0,'
        '"post_deadline_mono":55.0,"state":"ready","failure_reason":null,'
        '"clip":null,"report_json":null,"report_html":null,"transitions":[]}'
    )

    loaded = store.load("inc-1")

    assert (loaded.pre_seconds, loaded.post_seconds) == (30.0, 15.0)


def test_store_normalizes_malformed_existing_metadata_to_value_error(tmp_path: Path):
    store = IncidentStore(tmp_path)
    directory = store.directory("inc-1")
    directory.mkdir(parents=True)
    (directory / "metadata.json").write_text('{"incident_id":"inc-1"}')

    with pytest.raises(ValueError, match="metadata"):
        store.load("inc-1")


def test_retention_skips_protected_segments(tmp_path: Path):
    segments = [Segment(tmp_path / f"{n}.mp4", n, n + 2) for n in (0, 2, 4)]
    assert choose_prunable_segments(segments, {segments[0].path}, bytes_to_free=2, sizes={s.path: 2 for s in segments}) == [segments[1]]


def test_retention_selects_nothing_without_pressure(tmp_path: Path):
    segment = Segment(tmp_path / "0.mp4", 0, 2)
    assert choose_prunable_segments([segment], set(), bytes_to_free=0, sizes={segment.path: 2}) == []


def test_pressure_enforces_raw_and_free_space_limits():
    assert bytes_to_free(total=1000, used=950, raw_bytes=800, raw_max_fraction=.70, min_free_fraction=.10) == 100


def test_cleanup_removes_only_unreferenced_partials(tmp_path: Path):
    store = IncidentStore(tmp_path); active = tmp_path / "active.partial"; stale = tmp_path / "stale.partial"
    active.write_bytes(b"a"); stale.write_bytes(b"s")
    assert store.cleanup_stale_partials({active}) == [stale]
    assert active.exists() and not stale.exists()
