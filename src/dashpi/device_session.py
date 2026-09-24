"""Manual incident capture and delayed stop for the native device UI."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
import shutil
import time
import uuid

from dashpi.analysis_worker import AnalysisWorker
from dashpi.config import Settings
from dashpi.incidents import IncidentCoordinator, segments_for_window
from dashpi.models import IncidentMetadata, IncidentState, Segment
from dashpi.pipeline import IncidentPipeline
from dashpi.storage import IncidentStore, atomic_write, bytes_to_free, choose_prunable_segments


class DeviceSession:
    def __init__(
        self,
        recorder,
        settings: Settings,
        store: IncidentStore,
        worker: AnalysisWorker,
        analyze: Callable,
        detector=None,
    ):
        self.recorder, self.settings, self.store = recorder, settings, store
        self.worker, self.analyze, self.detector = worker, analyze, detector
        self.coordinator = IncidentCoordinator(settings, lambda: uuid.uuid4().hex)
        self.pending_stop = False
        self.last_error: str | None = None
        self._last_split = 0.0
        self._pending: list[tuple[Future, set[Path]]] = []
        self._failed_paths: set[Path] = set()

    def start(self, mode: str) -> None:
        self.settings.data_root.mkdir(parents=True, exist_ok=True)
        if not self.prune_raw(time.monotonic()):
            raise RuntimeError("저장 공간이 부족해 녹화를 시작할 수 없습니다.")
        self.recorder.start(mode)
        self._last_split = self.recorder.start_mono
        self.pending_stop = False
        self.last_error = None

    def trigger(self, now: float) -> IncidentMetadata:
        if not self.recorder.recording:
            raise RuntimeError("녹화 중이 아닙니다.")
        if now < self.recorder.start_mono:
            raise RuntimeError("녹화 시작 전 사고는 기록할 수 없습니다.")
        incident = self.coordinator.trigger(now, datetime.now(UTC).isoformat())
        self.store.save(incident)
        return incident

    def stop(self, now: float) -> bool:
        if not self.recorder.recording:
            return True
        had_active = bool(self.coordinator.active)
        self.tick(now)
        if not self.recorder.recording:
            return True
        if self.coordinator.active:
            self.pending_stop = True
            return False
        self.recorder.stop(allow_empty_tail=had_active)
        return True

    def tick(self, now: float) -> None:
        if not self.recorder.recording:
            return
        ready = self.coordinator.ready_at(now)
        if now - self._last_split >= self.recorder.segment_seconds or (
            ready and self._last_split < min(item.post_deadline_mono for item in ready)
        ):
            try:
                self.recorder.split()
                self._last_split = now
            except Exception as error:
                self._capture_failed(error)
                return
        for incident in ready:
            segments = segments_for_window(
                self.recorder.segments,
                incident.trigger_mono - self.settings.pre_seconds,
                incident.post_deadline_mono,
            )
            if not segments or segments[-1].end_mono < incident.post_deadline_mono:
                continue
            pipeline = IncidentPipeline(self.settings, self.store, self.detector)
            job = self.worker.submit(
                lambda incident=incident, segments=segments, pipeline=pipeline:
                pipeline.process(incident, segments, self.analyze)
            )
            if isinstance(job, Future):
                self._pending.append((job, {segment.path for segment in segments}))
            self.coordinator.active.remove(incident)
        if self.pending_stop and not self.coordinator.active:
            self.recorder.stop(allow_empty_tail=True)
            self.pending_stop = False
        elif self.recorder.recording and not self.prune_raw(now):
            self._capture_failed(RuntimeError("저장 공간이 부족합니다."))

    def prune_raw(self, now: float) -> bool:
        raw_dir = self.settings.data_root / "raw"
        files = [path for path in raw_dir.rglob("*.mp4") if path.is_file()]
        sizes = {path: path.stat().st_size for path in files}
        usage = shutil.disk_usage(self.settings.data_root)
        needed = bytes_to_free(
            usage.total, usage.used, sum(sizes.values()),
            self.settings.raw_max_fraction, self.settings.min_free_fraction,
        )
        if needed <= 0:
            return True
        protected: set[Path] = self._failed_paths.copy()
        protected.update(path for path in files if (path.parent / "incomplete_capture.txt").exists())
        protected.update({
            segment.path for segment in self.recorder.segments
            if self.recorder.recording and segment.end_mono > now - self.settings.pre_seconds
        })
        for incident in self.coordinator.active:
            protected.update(
                segment.path for segment in segments_for_window(
                    self.recorder.segments,
                    incident.trigger_mono - self.settings.pre_seconds,
                    incident.post_deadline_mono,
                )
            )
        self._pending = [(job, paths) for job, paths in self._pending if not job.done()]
        for _job, paths in self._pending:
            protected.update(paths)
        if self.recorder.recording and getattr(self.recorder, "current_path", None) is not None:
            protected.add(self.recorder.current_path)
        # File mtime orders raw footage across reboots, where monotonic clocks reset.
        candidates = [Segment(path, path.stat().st_mtime, path.stat().st_mtime + 1) for path in files]
        chosen = choose_prunable_segments(candidates, protected, needed, sizes)
        freed = 0
        for segment in chosen:
            segment.path.unlink()
            freed += sizes[segment.path]
        if chosen:
            deleted = {segment.path for segment in chosen}
            self.recorder.segments = [segment for segment in self.recorder.segments if segment.path not in deleted]
        return freed >= needed

    def _capture_failed(self, error: Exception) -> None:
        self.last_error = str(error)
        if self.coordinator.active:
            self._failed_paths.update(segment.path for segment in self.recorder.segments)
            session_dir = getattr(self.recorder, "session_dir", None)
            if session_dir is not None:
                with suppress(OSError):
                    atomic_write(session_dir / "incomplete_capture.txt", str(error).encode())
        for incident in self.coordinator.active:
            incident.transition(
                IncidentState.CLIP_FAILED,
                datetime.now(UTC).isoformat(),
                f"incomplete capture: {error}",
            )
            self.store.save(incident)
        self.coordinator.active.clear()
        self.pending_stop = False
        with suppress(Exception):
            self.recorder.stop()
