from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from dashpi.models import FileArtifact, IncidentMetadata, IncidentState, Segment


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, data: bytes) -> FileArtifact:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    with partial.open("wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    digest, byte_length = sha256_file(partial), partial.stat().st_size
    partial.replace(path)
    return FileArtifact(path, byte_length, digest)


class IncidentStore:
    def __init__(self, root: Path):
        self.root = root

    def directory(self, incident_id: str) -> Path:
        if not incident_id or len(incident_id) > 64 or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for character in incident_id
        ):
            raise KeyError("invalid incident id")
        return self.root / "incidents" / incident_id

    def save(self, item: IncidentMetadata) -> None:
        atomic_write(
            self.directory(item.incident_id) / "metadata.json",
            json.dumps(item.to_dict(), default=str, sort_keys=True).encode(),
        )

    def load(self, incident_id: str) -> IncidentMetadata:
        raw = json.loads((self.directory(incident_id) / "metadata.json").read_text())
        raw["state"] = IncidentState(raw["state"])
        raw.setdefault("pre_seconds", 30.0)
        raw.setdefault("post_seconds", raw["post_deadline_mono"] - raw["trigger_mono"])
        for key in ("clip", "report_json", "report_html"):
            if raw.get(key):
                raw[key] = FileArtifact(
                    Path(raw[key]["path"]),
                    raw[key]["byte_length"],
                    raw[key]["sha256"],
                    raw[key].get("duration"),
                )
        return IncidentMetadata(**raw)

    def list(self) -> list[IncidentMetadata]:
        parent = self.root / "incidents"
        if not parent.exists():
            return []
        return sorted(
            (
                self.load(path.name)
                for path in parent.iterdir()
                if (path / "metadata.json").is_file()
            ),
            key=lambda item: item.triggered_at,
            reverse=True,
        )

    def cleanup_stale_partials(self, active: set[Path]) -> list[Path]:
        removed = []
        for path in self.root.rglob("*.partial"):
            if path in active:
                continue
            path.unlink()
            removed.append(path)
        return removed


def bytes_to_free(
    total: int,
    used: int,
    raw_bytes: int,
    raw_max_fraction: float,
    min_free_fraction: float,
) -> int:
    raw_excess = raw_bytes - int(total * raw_max_fraction)
    free_shortfall = int(total * min_free_fraction) - (total - used)
    return max(0, raw_excess, free_shortfall)


def choose_prunable_segments(
    segments: list[Segment], protected: set[Path], bytes_to_free: int, sizes: dict[Path, int]
) -> list[Segment]:
    if bytes_to_free <= 0:
        return []
    chosen, freed = [], 0
    for segment in sorted(segments, key=lambda value: value.start_mono):
        if segment.path in protected:
            continue
        chosen.append(segment)
        freed += sizes[segment.path]
        if freed >= bytes_to_free:
            break
    return chosen
