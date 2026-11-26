"""Hermetic-facing wrapper around the external ``graspreach`` web router.

The production client imports ``graspreach`` directly from the sibling project's
``src`` directory. If that import or any call fails, it falls back to a bounded
``python -m graspreach`` subprocess. Tests replace this client entirely, so no
network access is needed in the suite.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class WebSearchError(RuntimeError):
    """Raised when no usable web result can be obtained."""


@dataclass(frozen=True)
class WebSearchItem:
    url: str
    title: str = ""
    snippet: str = ""


@dataclass(frozen=True)
class WebPage:
    url: str
    text: str
    title: str = ""
    fetched_at: str = ""
    provider: str = ""


class WebClient(Protocol):
    """Minimal interface used by the orchestration layer."""

    async def search(self, query: str) -> list[WebSearchItem]: ...

    async def read(self, url: str) -> WebPage: ...

    async def gather(self, query: str) -> list[WebPage]: ...


class GraspreachWebClient:
    """Cached graspreach client with an in-process router and subprocess fallback."""

    def __init__(self) -> None:
        self._search_cache: dict[str, tuple[float, list[WebSearchItem]]] = {}
        self._page_cache: dict[str, tuple[float, WebPage]] = {}
        self._router: Any | None = None
        self._router_failed = False

    # --------------------------------------------------------------- graspreach

    def _src_path(self) -> Path:
        return Path(get_settings().GRASPREACH_SRC_PATH)

    def _python(self) -> str:
        settings = get_settings()
        if settings.GRASPREACH_PYTHON:
            return settings.GRASPREACH_PYTHON
        root = self._src_path().parent
        if os.name == "nt":
            candidate = root / ".venv" / "Scripts" / "python.exe"
        else:
            candidate = root / ".venv" / "bin" / "python"
        return str(candidate) if candidate.exists() else sys.executable

    def _router_instance(self) -> Any:
        if self._router is not None:
            return self._router
        if self._router_failed:
            raise WebSearchError("graspreach router is unavailable")
        src = self._src_path()
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        try:
            from graspreach import build_default_router
        except Exception as exc:  # pragma: no cover - environment dependent
            self._router_failed = True
            raise WebSearchError(f"graspreach import failed: {exc}") from exc
        self._router = build_default_router()
        return self._router

    def _subprocess_json(self, args: list[str], timeout: float) -> dict[str, Any]:
        env = os.environ.copy()
        src = str(self._src_path())
        env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
        completed = subprocess.run(
            [self._python(), "-m", "graspreach", "--json", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            check=False,
        )
        if completed.returncode != 0:
            raise WebSearchError(
                f"graspreach subprocess failed ({completed.returncode}): "
                f"{completed.stderr.strip()[:300]}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise WebSearchError("graspreach subprocess returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise WebSearchError("graspreach subprocess returned an unexpected payload")
        return payload

    # ----------------------------------------------------------------- caching

    @staticmethod
    def _cache_key(value: str) -> str:
        return value.strip().lower()

    def _fresh(self, key: str, cache: dict[str, tuple[float, Any]]) -> Any | None:
        entry = cache.get(key)
        if entry is None:
            return None
        expires, value = entry
        if time.monotonic() >= expires:
            cache.pop(key, None)
            return None
        return value

    def _store(self, key: str, value: Any, cache: dict[str, tuple[float, Any]]) -> None:
        ttl = max(0, get_settings().WEB_CACHE_TTL_SECONDS)
        cache[key] = (time.monotonic() + ttl, value)

    # -------------------------------------------------------------------- API

    async def search(self, query: str) -> list[WebSearchItem]:
        settings = get_settings()
        key = self._cache_key(query)
        cached = self._fresh(key, self._search_cache)
        if cached is not None:
            return cached

        items: list[WebSearchItem] = []
        try:
            from graspreach import SearchRequest

            router = self._router_instance()
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    router.search,
                    SearchRequest(
                        query=query,
                        num_results=settings.WEB_SEARCH_RESULTS,
                        timeout=settings.WEB_SEARCH_TIMEOUT_SECONDS,
                    ),
                ),
                timeout=settings.WEB_SEARCH_TIMEOUT_SECONDS + 1.0,
            )
            items = [
                WebSearchItem(url=str(item.url), title=str(item.title), snippet=str(item.snippet))
                for item in getattr(result, "items", [])
                if getattr(item, "url", "")
            ]
        except Exception as exc:
            logger.warning("graspreach in-process search failed; using subprocess: %s", exc)

        if not items:
            try:
                payload = await asyncio.to_thread(
                    self._subprocess_json,
                    ["search", query, "--num-results", str(settings.WEB_SEARCH_RESULTS)],
                    settings.WEB_SEARCH_TIMEOUT_SECONDS,
                )
                items = [
                    WebSearchItem(
                        url=str(item.get("url", "")),
                        title=str(item.get("title", "")),
                        snippet=str(item.get("snippet", "")),
                    )
                    for item in payload.get("items", [])
                    if str(item.get("url", ""))
                ]
            except Exception as exc:
                logger.warning("graspreach subprocess search failed: %s", exc)

        self._store(key, items, self._search_cache)
        return items

    async def read(self, url: str) -> WebPage:
        settings = get_settings()
        key = self._cache_key(url)
        cached = self._fresh(key, self._page_cache)
        if cached is not None:
            return cached

        page: WebPage | None = None
        try:
            from graspreach import FetchRequest

            router = self._router_instance()
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    router.read,
                    FetchRequest(
                        url=url,
                        max_bytes=settings.WEB_MAX_PAGE_BYTES,
                        timeout=settings.WEB_FETCH_TIMEOUT_SECONDS,
                    ),
                ),
                timeout=settings.WEB_FETCH_TIMEOUT_SECONDS + 1.0,
            )
            text = str(getattr(result, "markdown", "") or "")
            if text.strip():
                page = WebPage(
                    url=str(getattr(result, "url", url)),
                    text=text[: settings.WEB_MAX_PAGE_CHARS],
                    title=str(getattr(result, "title", "") or ""),
                    fetched_at=str(getattr(result, "extracted_at", "") or ""),
                    provider=str(getattr(result, "provider", "") or ""),
                )
        except Exception as exc:
            logger.warning("graspreach in-process read failed for %s; using subprocess: %s", url, exc)

        if page is None:
            try:
                payload = await asyncio.to_thread(
                    self._subprocess_json,
                    [
                        "fetch",
                        url,
                        "--max-bytes",
                        str(settings.WEB_MAX_PAGE_BYTES),
                    ],
                    settings.WEB_FETCH_TIMEOUT_SECONDS,
                )
                text = str(payload.get("markdown", "") or "")
                if text.strip():
                    page = WebPage(
                        url=str(payload.get("url", url)),
                        text=text[: settings.WEB_MAX_PAGE_CHARS],
                        title=str(payload.get("title", "") or ""),
                    )
            except Exception as exc:
                logger.warning("graspreach subprocess read failed for %s: %s", url, exc)

        if page is None:
            raise WebSearchError(f"no content fetched for {url}")
        self._store(key, page, self._page_cache)
        return page

    async def gather(self, query: str) -> list[WebPage]:
        settings = get_settings()
        try:
            async with asyncio.timeout(settings.WEB_TOTAL_BUDGET_SECONDS):
                items = await self.search(query)
                if not items:
                    return []
                results = await asyncio.gather(
                    *(self.read(item.url) for item in items[: settings.WEB_SEARCH_RESULTS]),
                    return_exceptions=True,
                )
                pages = [page for page in results if isinstance(page, WebPage)]
                if not pages:
                    raise WebSearchError("all web fetches failed")
                return pages
        except (TimeoutError, WebSearchError):
            raise
        except Exception as exc:
            raise WebSearchError(f"web grounding failed: {exc}") from exc


_client: WebClient | None = None


def get_web_client() -> WebClient:
    """Return the process-wide web client, creating it lazily."""
    global _client
    if _client is None:
        _client = GraspreachWebClient()
    return _client


def set_web_client(client: WebClient | None) -> None:
    """Replace the web client (used by tests and local tooling)."""
    global _client
    _client = client
