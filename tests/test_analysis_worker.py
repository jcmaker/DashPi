from threading import Event

from dashpi.analysis_worker import AnalysisWorker
from tests.media_factory import make_video


def test_analysis_waits_during_recording_pressure_without_blocking_caller():
    worker = AnalysisWorker()
    ran = Event()

    worker.pause()
    future = worker.submit(lambda: (worker.wait_for_capacity(), ran.set()))

    assert future.done() is False
    assert ran.is_set() is False

    worker.resume()
    future.result(timeout=2)

    assert ran.is_set()
    worker.close()


def test_worker_runs_only_one_analysis_at_a_time():
    worker = AnalysisWorker()
    first_release, second_started = Event(), Event()

    first = worker.submit(lambda: first_release.wait(2))
    second = worker.submit(second_started.set)

    assert not second_started.wait(0.1)

    first_release.set()
    first.result(timeout=2)
    second.result(timeout=2)
    worker.close()


def test_recording_continues_while_analysis_is_paused(tmp_path):
    worker = AnalysisWorker()
    worker.pause()

    future = worker.submit(lambda: (worker.wait_for_capacity(), "analyzed")[1])
    segment = make_video(tmp_path / "new-segment.mp4", 2)

    assert segment.exists() and not future.done()

    worker.resume()
    assert future.result(timeout=2) == "analyzed"
    worker.close()
