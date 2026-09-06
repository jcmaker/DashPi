from threading import Event
from pathlib import Path
import subprocess
import sys

import pytest

from dashpi.analysis_worker import AnalysisWorker
from tests.media_factory import make_video


@pytest.mark.parametrize("name", [
    "test_analysis_waits_during_recording_pressure_without_blocking_caller",
    "test_worker_runs_only_one_analysis_at_a_time",
    "test_recording_continues_while_analysis_is_paused",
])
def test_worker_tests_close_even_when_submission_raises(name, tmp_path):
    script = f'''
import sys
sys.path.insert(0, "src")
from pathlib import Path
import tests.test_analysis_worker as target
real_submit = target.AnalysisWorker.submit
def fail_after_submit(self, work):
    real_submit(self, work)
    raise RuntimeError("injected test failure")
target.AnalysisWorker.submit = fail_after_submit
try:
    getattr(target, {name!r})(*([Path({str(tmp_path)!r})] if {name!r}.endswith("is_paused") else []))
except RuntimeError:
    print("failure propagated", flush=True)
'''
    try:
        result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).parents[1], capture_output=True, text=True, timeout=1)
    except subprocess.TimeoutExpired:
        pytest.fail("paused worker survived a test exception and blocked process exit")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "failure propagated"


def test_analysis_waits_during_recording_pressure_without_blocking_caller():
    worker = AnalysisWorker()
    ran = Event()

    try:
        worker.pause()
        future = worker.submit(lambda: (worker.wait_for_capacity(), ran.set()))

        assert future.done() is False
        assert ran.is_set() is False

        worker.resume()
        future.result(timeout=2)

        assert ran.is_set()
    finally:
        worker.close()


def test_worker_runs_only_one_analysis_at_a_time():
    worker = AnalysisWorker()
    first_release, second_started = Event(), Event()

    try:
        first = worker.submit(lambda: first_release.wait(2))
        second = worker.submit(second_started.set)

        assert not second_started.wait(0.1)

        first_release.set()
        first.result(timeout=2)
        second.result(timeout=2)
    finally:
        first_release.set()
        worker.close()


def test_recording_continues_while_analysis_is_paused(tmp_path):
    worker = AnalysisWorker()
    try:
        worker.pause()

        future = worker.submit(lambda: (worker.wait_for_capacity(), "analyzed")[1])
        segment = make_video(tmp_path / "new-segment.mp4", 2)

        assert segment.exists() and not future.done()

        worker.resume()
        assert future.result(timeout=2) == "analyzed"
    finally:
        worker.close()
