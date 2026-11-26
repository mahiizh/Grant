"""Per-request stage timings for Ask diagnostics.

The timings are accumulated in a context variable so library code (retrievers,
embeddings, reranker) can record real durations without threading a collector
through every constructor. A request installs a fresh mapping in
:class:`RAGOrchestrator.run`; code outside a request is a no-op.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token
from functools import wraps
from typing import Any, TypeVar

_STAGE_TIMINGS: ContextVar[dict[str, float] | None] = ContextVar(
    "ask_stage_timings", default=None
)


def start_stage_timings() -> tuple[dict[str, float], Token[dict[str, float] | None]]:
    """Install and return a fresh timing map plus the token that restores the prior one."""
    timings: dict[str, float] = {}
    token = _STAGE_TIMINGS.set(timings)
    return timings, token


def end_stage_timings(token: Token[dict[str, float] | None]) -> None:
    _STAGE_TIMINGS.reset(token)


def current_stage_timings() -> dict[str, float] | None:
    return _STAGE_TIMINGS.get()


def record_stage(name: str, duration_ms: float) -> None:
    timings = _STAGE_TIMINGS.get()
    if timings is None:
        return
    timings[name] = round(timings.get(name, 0.0) + max(0.0, duration_ms), 2)


@asynccontextmanager
async def timed_stage(name: str) -> AsyncIterator[None]:
    """Record wall-clock time spent inside an async stage."""
    started = time.perf_counter()
    try:
        yield
    finally:
        record_stage(name, (time.perf_counter() - started) * 1000.0)


@contextmanager
def timed_stage_sync(name: str) -> Iterator[None]:
    """Record wall-clock time spent inside a synchronous stage."""
    started = time.perf_counter()
    try:
        yield
    finally:
        record_stage(name, (time.perf_counter() - started) * 1000.0)


def timing_snapshot() -> dict[str, float]:
    """Return a plain copy suitable for API responses and state payloads."""
    return dict(_STAGE_TIMINGS.get() or {})


F = TypeVar("F", bound=Callable[..., Coroutine[Any, Any, Any]])


def timed_async_stage(name: str) -> Callable[[F], F]:
    """Decorator form of :func:`timed_stage` for async retriever methods."""

    def decorate(fn: F) -> F:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            async with timed_stage(name):
                return await fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorate
