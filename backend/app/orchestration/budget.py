"""Hard end-to-end budget for Ask/chat requests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Any, TypeVar

from app.core.config import get_settings

T = TypeVar("T")


class AskBudgetExceededError(TimeoutError):
    """Raised when a single Ask request exceeds its total wall-clock budget."""


async def run_with_ask_budget(operation: Awaitable[T], settings: Any | None = None) -> T:
    """Bound the whole orchestration run, including retrieval, web, and LLM."""
    resolved = settings or get_settings()
    try:
        return await asyncio.wait_for(
            operation, timeout=resolved.ASK_TOTAL_BUDGET_SECONDS
        )
    except TimeoutError as exc:
        raise AskBudgetExceededError(
            f"Ask request exceeded {resolved.ASK_TOTAL_BUDGET_SECONDS:g}s budget"
        ) from exc
