"""Tests for bounded graspreach reads in the API-side web client."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from app.core.config import get_settings
from app.web_grounding.web import GraspreachWebClient, WebSearchError


@dataclass(frozen=True)
class _SearchRequest:
    query: str
    num_results: int
    timeout: float


@dataclass(frozen=True)
class _FetchRequest:
    url: str
    max_bytes: int
    timeout: float


@dataclass
class _SearchItem:
    url: str
    title: str = ""
    snippet: str = ""


@dataclass
class _SearchResult:
    query: str
    items: list[_SearchItem] = field(default_factory=list)
    provider: str = ""


@dataclass
class _FetchResult:
    url: str
    markdown: str
    title: str = ""
    provider: str = "jina"
    extracted_at: str = "2026-11-26T00:00:00Z"


class FakeRouter:
    def __init__(
        self,
        items: list[_SearchItem],
        reader: Callable[[str], _FetchResult],
        provider: str = "exa",
    ) -> None:
        self.items = items
        self.reader = reader
        self.provider = provider
        self.fetch_requests: list[_FetchRequest] = []
        self.search_requests: list[_SearchRequest] = []
        self.active_reads = 0
        self.max_active_reads = 0
        self._lock = threading.Lock()

    def search(self, request: _SearchRequest) -> _SearchResult:
        self.search_requests.append(request)
        return _SearchResult(query=request.query, items=self.items, provider=self.provider)

    def read(self, request: _FetchRequest) -> _FetchResult:
        with self._lock:
            self.fetch_requests.append(request)
            self.active_reads += 1
            self.max_active_reads = max(self.max_active_reads, self.active_reads)
        try:
            time.sleep(0.05)
            return self.reader(request.url)
        finally:
            with self._lock:
                self.active_reads -= 1


def install_router(monkeypatch: pytest.MonkeyPatch, router: FakeRouter) -> None:
    fake_module = SimpleNamespace(SearchRequest=_SearchRequest, FetchRequest=_FetchRequest)
    monkeypatch.setitem(sys.modules, "graspreach", fake_module)
    monkeypatch.setattr(GraspreachWebClient, "_router_instance", lambda self: router)


def search_items(count: int, *, with_text: bool = False) -> list[_SearchItem]:
    return [
        _SearchItem(
            url=f"https://example.com/page_{index}",
            title=f"Page {index}",
            snippet="Exa returned this useful passage. " * 8 if with_text else "",
        )
        for index in range(count)
    ]


@pytest.mark.anyio
async def test_exa_returned_text_is_used_without_a_second_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = FakeRouter(
        search_items(3, with_text=True),
        reader=lambda url: (_ for _ in ()).throw(AssertionError(f"unexpected fetch: {url}")),
        provider="exa",
    )
    install_router(monkeypatch, router)

    pages = await GraspreachWebClient().gather("what is tungsten's symbol")

    assert len(pages) == 3
    assert {page.provider for page in pages} == {"exa"}
    assert pages[0].text.startswith("Exa returned this useful passage.")
    assert router.fetch_requests == []


@pytest.mark.anyio
async def test_oversized_pages_are_truncated_and_fetched_in_parallel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "WEB_MAX_PAGE_CHARS", 24)
    monkeypatch.setattr(settings, "WEB_FETCH_MAX_BYTES", 4096)
    monkeypatch.setattr(settings, "WEB_FETCH_TIMEOUT_SECONDS", 5.0)
    router = FakeRouter(
        search_items(5),
        reader=lambda url: _FetchResult(url=url, markdown="x" * 100_000),
        provider="jina",
    )
    install_router(monkeypatch, router)

    pages = await GraspreachWebClient().gather("oversized pages")

    assert len(pages) == 3  # at most three pages, even with five search hits
    assert all(len(page.text) == 24 for page in pages)
    assert len(router.fetch_requests) == 3
    assert all(request.max_bytes == 4096 for request in router.fetch_requests)
    assert all(request.timeout == 5.0 for request in router.fetch_requests)
    assert router.max_active_reads > 1
    assert settings.WEB_TOTAL_BUDGET_SECONDS == 12.0


@pytest.mark.anyio
async def test_captcha_pages_are_dropped_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reader(url: str) -> _FetchResult:
        if "page_1" in url:
            return _FetchResult(
                url=url,
                markdown="Just a moment...\nPerforming security verification",
            )
        return _FetchResult(url=url, markdown=f"Useful content for {url}")

    router = FakeRouter(search_items(3), reader=reader, provider="jina")
    install_router(monkeypatch, router)
    client = GraspreachWebClient()

    with pytest.raises(WebSearchError):
        await client.read("https://example.com/page_1")

    pages = await client.gather("captcha page")
    assert len(pages) == 2
    assert all("page_1" not in page.url for page in pages)
    assert len(router.fetch_requests) == 4  # one dropped read + three gather reads
