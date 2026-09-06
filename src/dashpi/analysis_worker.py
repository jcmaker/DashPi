from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
from typing import TypeVar


T = TypeVar("T")


class AnalysisWorker:
    def __init__(self):
        self._capacity = Event()
        self._capacity.set()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dashpi-analysis")

    def pause(self) -> None:
        self._capacity.clear()

    def resume(self) -> None:
        self._capacity.set()

    def wait_for_capacity(self) -> None:
        self._capacity.wait()

    def submit(self, work: Callable[[], T]) -> Future[T]:
        return self._executor.submit(work)

    def close(self) -> None:
        self._capacity.set()
        self._executor.shutdown(wait=True, cancel_futures=True)
