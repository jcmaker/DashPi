from datetime import datetime, timedelta, timezone
import json

import pytest

from dashpi.ai_budget import DailyBudget
from dashpi.ai_client import RetryableAnalysisError

KST = timezone(timedelta(hours=9))


def test_limit_blocks_until_five_past_midnight_next_day(tmp_path):
    now = datetime(2026, 9, 25, 22, 0, tzinfo=KST)
    budget = DailyBudget(tmp_path / "ai-usage.json", 2, lambda: now)
    budget.check()
    budget.record()
    budget.check()
    budget.record()
    with pytest.raises(RetryableAnalysisError, match="한도") as error:
        budget.check()
    assert error.value.retry_at == datetime(2026, 9, 26, 0, 5, tzinfo=KST)


def test_check_does_not_spend(tmp_path):
    path = tmp_path / "ai-usage.json"
    budget = DailyBudget(path, 1, lambda: datetime(2026, 9, 25, tzinfo=KST))
    for _ in range(3):
        budget.check()
    assert not path.exists()
    budget.record()
    assert json.loads(path.read_text()) == {"date": "2026-09-25", "count": 1}


def test_count_resets_on_a_new_day(tmp_path):
    clock = [datetime(2026, 9, 25, 23, 0, tzinfo=KST)]
    budget = DailyBudget(tmp_path / "ai-usage.json", 1, lambda: clock[0])
    budget.record()
    clock[0] += timedelta(hours=2)
    budget.check()


def test_corrupt_usage_file_starts_fresh(tmp_path):
    path = tmp_path / "ai-usage.json"
    path.write_text("{not json")
    budget = DailyBudget(path, 1, lambda: datetime(2026, 9, 25, tzinfo=KST))
    budget.check()
    budget.record()
    assert json.loads(path.read_text())["count"] == 1
