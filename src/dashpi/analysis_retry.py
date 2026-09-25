"""Re-run analysis for incidents waiting on network, provider, key, or daily limit."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from datetime import UTC, datetime
import logging

from dashpi.models import IncidentState
from dashpi.storage import IncidentStore

log = logging.getLogger("dashpi")


class AnalysisRetrier:
    def __init__(self, store: IncidentStore, run: Callable[[str], Future],
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.store, self.run, self.now = store, run, now
        self._running: tuple[str, Future] | None = None

    def recover_interrupted(self) -> list[str]:
        recovered = []
        now = self.now().isoformat()
        for item in self.store.list(states=set(IncidentState)):
            if item.state is IncidentState.ANALYZING:
                item.next_analysis_at = now
                item.transition(IncidentState.AWAITING_ANALYSIS, now, "분석 중 앱이 종료되어 다시 분석합니다")
                self.store.save(item)
                recovered.append(item.incident_id)
        return recovered

    def tick(self) -> str | None:
        if self._running is not None:
            incident_id, future = self._running
            if not future.done():
                return None
            self._running = None
            if future.exception() is not None:
                self._mark_failed(incident_id, future.exception())
        now = self.now()
        due = [
            item for item in self.store.list(states=set(IncidentState))
            if item.state is IncidentState.AWAITING_ANALYSIS
            and (item.next_analysis_at is None or datetime.fromisoformat(item.next_analysis_at) <= now)
        ]
        if not due:
            return None
        earliest = datetime.min.replace(tzinfo=UTC)
        item = min(due, key=lambda entry: datetime.fromisoformat(entry.next_analysis_at)
                   if entry.next_analysis_at else earliest)
        log.info("분석 재시도: %s (%s)", item.incident_id, item.failure_reason)
        item.transition(IncidentState.ANALYZING, now.isoformat())
        self.store.save(item)
        self._running = (item.incident_id, self.run(item.incident_id))
        return item.incident_id

    def _mark_failed(self, incident_id: str, error: BaseException) -> None:
        log.error("분석 재시도 실패: %s", incident_id, exc_info=error)
        try:
            item = self.store.load(incident_id)
        except ValueError:
            return
        if item.state in (IncidentState.AWAITING_ANALYSIS, IncidentState.ANALYZING):
            item.transition(IncidentState.ANALYSIS_FAILED, self.now().isoformat(), f"재분석 불가: {error}")
            self.store.save(item)
