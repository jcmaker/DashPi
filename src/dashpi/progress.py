"""Live analysis progress for a waiting screen; silent unless the caller installs a listener."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

Listener = Callable[[str, str, str, object], None]
_listener: ContextVar[Listener | None] = ContextVar("dashpi_progress", default=None)


def emit(step: str, state: str, detail: str = "", payload: object = None) -> None:
    listener = _listener.get()
    if listener is not None:
        listener(step, state, detail, payload)


@contextmanager
def reporting(listener: Listener) -> Iterator[None]:
    token = _listener.set(listener)
    try:
        yield
    finally:
        _listener.reset(token)
