import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.routes import query as query_route
from app.api.routes import threads as threads_route
from app.core.config import get_settings
from app.db.models import Base
from app.db.postgres import get_db_session
from app.llm import gateway as gateway_module
from app.llm.gateway import ModelGateway
from app.main import app
from tests.fakes.hermetic import build_hermetic_orchestrator, load_corpus_chunks


def parse_sse(payload: str) -> list[tuple[str, object]]:
    events: list[tuple[str, object]] = []
    for block in payload.split("\n\n"):
        if not block.strip():
            continue
        event = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
        if event and data:
            events.append((event, json.loads(data)))
    return events


@pytest.mark.anyio
async def test_stream_complete_forwards_provider_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_CACHE_ENABLED", False)

    async def fake_acompletion(**kwargs: object) -> object:
        assert kwargs["stream"] is True

        async def chunks() -> AsyncGenerator[SimpleNamespace, None]:
            for text in ("Alpha ", "beta ", "gamma"):
                delta = SimpleNamespace(content=text)
                yield SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=None)

        return chunks()

    monkeypatch.setattr(gateway_module.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(
        gateway_module.litellm,
        "token_counter",
        lambda model, messages=None, text=None, **_: 10 if messages is not None else 3,
    )
    monkeypatch.setattr(gateway_module.litellm, "completion_cost", lambda **_: 0.00002)

    gateway = ModelGateway(default_model="gemini/gemini-3.5-flash-lite")
    tokens: list[str] = []
    response = await gateway.stream_complete(prompt="hello", on_token=tokens.append)

    assert tokens == ["Alpha ", "beta ", "gamma"]
    assert response.content == "Alpha beta gamma"
    assert response.usage.completion_tokens == 3


@pytest.fixture
async def streaming_client(
    tmp_corpus_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncClient, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    session = factory()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_db_session] = override_get_db

    @asynccontextmanager
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield session

    monkeypatch.setattr(threads_route, "get_session", override_get_session)
    previous_orchestrator = query_route.get_orchestrator()
    orchestrator = build_hermetic_orchestrator(load_corpus_chunks(tmp_corpus_dir))[0]
    query_route.set_orchestrator(orchestrator)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Dev-User": "admin"},
        ) as client:
            yield client
    finally:
        query_route.set_orchestrator(previous_orchestrator)
        app.dependency_overrides.clear()
        await session.close()
        await engine.dispose()


@pytest.mark.anyio
async def test_query_stream_emits_tokens_then_metadata(streaming_client: AsyncClient) -> None:
    response = await streaming_client.post(
        "/api/v1/query/stream",
        json={
            "query": "Which database acts as the single source of truth?",
            "answer_policy": "grounded_only",
        },
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    token_events = [data for event, data in events if event == "token"]
    done_events = [data for event, data in events if event == "done"]
    error_events = [data for event, data in events if event == "error"]

    assert token_events
    assert not error_events
    assert len(done_events) == 1
    done = done_events[0]
    assert "".join(str(item["token"]) for item in token_events) == done["answer"]
    assert done["source"] in {"docs", "web", "model", "abstain"}
    assert isinstance(done["answer_path"], list)
    assert isinstance(done["top_score"], (int, float))
    assert isinstance(done["stage_timings_ms"], dict)
    assert isinstance(done["ttft_ms"], (int, float))


@pytest.mark.anyio
async def test_thread_stream_emits_real_tokens(streaming_client: AsyncClient) -> None:
    created = await streaming_client.post("/api/v1/threads", json={"title": "Streaming"})
    assert created.status_code == 201
    thread_id = created.json()["thread_id"]

    response = await streaming_client.post(
        f"/api/v1/threads/{thread_id}/messages?stream=true",
        headers={"Accept": "text/event-stream"},
        json={"content": "Which database acts as the single source of truth?"},
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    token_events = [data for event, data in events if event == "token"]
    done_events = [data for event, data in events if event == "done"]
    error_events = [data for event, data in events if event == "error"]

    assert token_events
    assert not error_events
    assert len(done_events) == 1
    done = done_events[0]
    assert "".join(str(item["token"]) for item in token_events) == done["content"]
    assert isinstance(done["ttft_ms"], (int, float))
    assert done["source"] in {"docs", "web", "model", "abstain"}
    assert isinstance(done["answer_path"], list)
    assert isinstance(done["top_score"], (int, float))
    assert isinstance(done["stage_timings_ms"], dict)
