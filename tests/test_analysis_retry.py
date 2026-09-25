from concurrent.futures import Future
from datetime import UTC, datetime, timedelta

from dashpi.analysis_retry import AnalysisRetrier
from dashpi.models import IncidentMetadata, IncidentState
from dashpi.storage import IncidentStore

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def awaiting(store, incident_id, due, state=IncidentState.AWAITING_ANALYSIS):
    item = IncidentMetadata.new(incident_id, NOW.isoformat(), 10.0, 15.0)
    item.next_analysis_at = None if due is None else due.isoformat()
    item.transition(state, NOW.isoformat(), "인터넷 연결 없음")
    store.save(item)


def test_due_incidents_run_one_at_a_time_earliest_first(tmp_path):
    store = IncidentStore(tmp_path)
    awaiting(store, "later", NOW - timedelta(minutes=1))
    awaiting(store, "first", NOW - timedelta(minutes=5))
    awaiting(store, "future", NOW + timedelta(minutes=5))
    submitted, pending = [], Future()
    retrier = AnalysisRetrier(store, lambda incident_id: submitted.append(incident_id) or pending, lambda: NOW)

    assert retrier.tick() == "first"
    assert retrier.tick() is None  # still running
    pending.set_result(None)
    assert retrier.tick() == "later"
    assert submitted == ["first", "later"]


def test_mixed_time_zones_are_ordered_by_instant(tmp_path):
    from datetime import timezone
    store = IncidentStore(tmp_path)
    awaiting(store, "utc-later", NOW - timedelta(minutes=1))
    awaiting(store, "kst-earlier", (NOW - timedelta(minutes=30)).astimezone(timezone(timedelta(hours=9))))
    done = Future()
    done.set_result(None)
    assert AnalysisRetrier(store, lambda _id: done, lambda: NOW).tick() == "kst-earlier"


def test_metadata_without_next_time_is_due_immediately(tmp_path):
    store = IncidentStore(tmp_path)
    awaiting(store, "old", None)
    done = Future()
    done.set_result(None)
    assert AnalysisRetrier(store, lambda _id: done, lambda: NOW).tick() == "old"


def test_interrupted_analysis_is_recovered_on_startup(tmp_path):
    store = IncidentStore(tmp_path)
    awaiting(store, "cut", NOW, state=IncidentState.ANALYZING)
    retrier = AnalysisRetrier(store, lambda _id: Future(), lambda: NOW)

    assert retrier.recover_interrupted() == ["cut"]
    loaded = store.load("cut")
    assert loaded.state is IncidentState.AWAITING_ANALYSIS and loaded.next_analysis_at == NOW.isoformat()


def test_run_that_raises_marks_the_incident_failed(tmp_path):
    store = IncidentStore(tmp_path)
    awaiting(store, "broken", NOW - timedelta(seconds=1))
    failed = Future()
    failed.set_exception(ValueError("invalid evidence clip"))
    retrier = AnalysisRetrier(store, lambda _id: failed, lambda: NOW)

    retrier.tick()
    retrier.tick()

    loaded = store.load("broken")
    assert loaded.state is IncidentState.ANALYSIS_FAILED and "invalid evidence clip" in loaded.failure_reason
