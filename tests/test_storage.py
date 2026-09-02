from pathlib import Path

from dashpi.models import IncidentMetadata, Segment
from dashpi.storage import IncidentStore, atomic_write, bytes_to_free, choose_prunable_segments


def test_atomic_write_leaves_only_complete_file(tmp_path: Path):
    artifact = atomic_write(tmp_path / "report.json", b'{"ok":true}')
    assert artifact.path.read_bytes() == b'{"ok":true}'
    assert artifact.sha256 == "4062edaf750fb8074e7e83e0c9028c94e32468a8b6f1614774328ef045150f93"
    assert not (tmp_path / "report.json.partial").exists()


def test_store_round_trips_incident(tmp_path: Path):
    store = IncidentStore(tmp_path)
    store.save(IncidentMetadata.new("inc-1", "2026-09-02T00:00:00Z", 40.0, 15.0))
    assert store.load("inc-1").incident_id == "inc-1"


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
