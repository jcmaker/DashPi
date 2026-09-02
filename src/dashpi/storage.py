from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import BinaryIO

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
        with self.open_incident(incident_id) as (item, _descriptor, _directory):
            return item

    @contextmanager
    def open_incident(
        self, incident_id: str
    ) -> Iterator[tuple[IncidentMetadata, int, Path]]:
        directory = self.directory(incident_id)
        incidents_descriptor = _open_directory(self.root / "incidents")
        try:
            incident_descriptor = _open_directory(incident_id, dir_fd=incidents_descriptor)
        finally:
            os.close(incidents_descriptor)
        try:
            with open_regular_file_at(incident_descriptor, "metadata.json") as metadata_source:
                raw = json.loads(metadata_source.read())
            item = self._metadata_from_raw(raw)
            yield item, incident_descriptor, directory
        finally:
            os.close(incident_descriptor)

    @staticmethod
    def _metadata_from_raw(raw: dict) -> IncidentMetadata:
        try:
            if type(raw) is not dict:
                raise ValueError("metadata is not an object")
            raw = raw.copy()
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
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise ValueError("invalid incident metadata") from error

    def list(self) -> list[IncidentMetadata]:
        parent = self.root / "incidents"
        try:
            parent_descriptor = _open_directory(parent)
        except (FileNotFoundError, OSError):
            return []
        try:
            if os.listdir not in getattr(os, "supports_fd", ()):
                return []
            incident_ids = os.listdir(parent_descriptor)
        finally:
            os.close(parent_descriptor)
        summary_states = {
            IncidentState.READY,
            IncidentState.CLIP_FAILED,
            IncidentState.ANALYSIS_FAILED,
        }
        items = []
        for incident_id in incident_ids:
            try:
                item = self.load(incident_id)
            except (FileNotFoundError, KeyError, OSError, TypeError, ValueError):
                continue
            if item.state in summary_states:
                items.append(item)
        return sorted(
            items,
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


def open_regular_file_at(directory_descriptor: int, basename: str) -> BinaryIO:
    if not basename or basename in {".", ".."} or Path(basename).name != basename:
        raise OSError("file must be a fixed basename")
    flags = _secure_open_flags(directory=False)
    if (
        os.open not in getattr(os, "supports_dir_fd", ())
        or os.stat not in getattr(os, "supports_dir_fd", ())
        or os.stat not in getattr(os, "supports_follow_symlinks", ())
    ):
        raise OSError("descriptor-relative file access is unavailable")
    expected = os.stat(
        basename,
        dir_fd=directory_descriptor,
        follow_symlinks=False,
    )
    if not stat.S_ISREG(expected.st_mode):
        raise OSError("artifact is not a regular file")
    descriptor = os.open(basename, flags, dir_fd=directory_descriptor)
    try:
        source = os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise
    try:
        details = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(details.st_mode)
            or (details.st_dev, details.st_ino) != (expected.st_dev, expected.st_ino)
        ):
            raise OSError("artifact changed during open")
        return source
    except BaseException:
        source.close()
        raise


def _open_directory(path: Path | str, *, dir_fd: int | None = None) -> int:
    flags = _secure_open_flags(directory=True)
    if dir_fd is None:
        return os.open(path, flags)
    if os.open not in getattr(os, "supports_dir_fd", ()):
        raise OSError("descriptor-relative directory access is unavailable")
    return os.open(path, flags, dir_fd=dir_fd)


def _secure_open_flags(*, directory: bool) -> int:
    if not hasattr(os, "O_NOFOLLOW") or (directory and not hasattr(os, "O_DIRECTORY")):
        raise OSError("secure descriptor flags are unavailable")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if directory:
        flags |= os.O_DIRECTORY
    return flags
