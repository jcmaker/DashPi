"""Per-device daily cap on analyses — the second line of defence behind the provider key limit."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, time, timedelta
import json
from pathlib import Path

from dashpi.ai_client import RetryableAnalysisError
from dashpi.storage import atomic_write


class DailyBudget:
    def __init__(self, path: Path, limit: int,
                 now: Callable[[], datetime] = lambda: datetime.now().astimezone()):
        self.path, self.limit, self.now = path, limit, now

    def _today_count(self) -> tuple[datetime, int]:
        now = self.now()
        try:
            raw = json.loads(self.path.read_text())
            count = raw["count"] if raw.get("date") == now.date().isoformat() and isinstance(raw.get("count"), int) else 0
        except (OSError, ValueError, AttributeError):
            count = 0
        return now, count

    def check(self) -> None:
        now, count = self._today_count()
        if count >= self.limit:
            resume = datetime.combine(now.date() + timedelta(days=1), time(0, 5), tzinfo=now.tzinfo)
            raise RetryableAnalysisError("오늘 분석 한도 도달", retry_at=resume)

    def record(self) -> None:
        now, count = self._today_count()
        atomic_write(self.path, json.dumps({"date": now.date().isoformat(), "count": count + 1}).encode())
