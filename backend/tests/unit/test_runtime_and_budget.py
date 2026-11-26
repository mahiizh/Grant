import asyncio
import threading
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI

import app.runtime as runtime
from app.api.routes import threads as threads_module
from app.core.config import get_settings
from app.graph.retrievers import GraphRetriever
from app.history import service as history_service
from app.llm import gateway as gateway_module
from app.llm.gateway import ModelGateway
from app.orchestration.budget import AskBudgetExceededError, run_with_ask_budget
from app.retrieval.embeddings import EmbeddingService
from app.retrieval.filters import RetrievalFilter


class FakeModels:
    def __init__(self) -> None:
        self.warmups = 0
        self.dense_model_name = "fake-dense"
        self.sparse_model_name = "fake-sparse"
        self.rerank_model_name = "fake-rerank"

    def warmup(self) -> None:
        self.warmups += 1


@pytest.mark.anyio
async def test_lifespan_builds_and_warms_models_once(monkeypatch: Any) -> None:
    from app.main import lifespan

    calls: list[str] = []

    async def fake_verify() -> None:
        calls.append("verify")

    monkeypatch.setattr("app.main.verify_infrastructure_live", fake_verify)

    async def fake_startup() -> None:
        calls.append("models")

    monkeypatch.setattr("app.main.startup_models", fake_startup)
    monkeypatch.setattr("app.main.shutdown_models", lambda: calls.append("shutdown"))

    async with lifespan(FastAPI()):
        pass

    assert calls == ["verify", "models", "shutdown"]


@pytest.mark.anyio
async def test_startup_builds_shared_bundle_and_warms_it(monkeypatch: Any) -> None:
    built: list[FakeModels] = []

    def build() -> FakeModels:
        models = FakeModels()
        models.warmup()
        built.append(models)
        return models

    monkeypatch.setattr(runtime, "_models", None)
    monkeypatch.setattr(runtime, "_build_models", build)
    monkeypatch.setattr(get_settings(), "APP_ENV", "development")

    await runtime.startup_models()

    assert len(built) == 1
    assert built[0].warmups == 1
    assert runtime.get_models() is built[0]
    assert runtime.get_models() is built[0]


@pytest.mark.anyio
async def test_off_loop_runs_on_bounded_model_pool() -> None:
    thread_name = await runtime.off_loop(lambda: threading.current_thread().name)
    assert thread_name.startswith("model")


@pytest.mark.anyio
async def test_embedding_facade_is_lazy_until_an_inference_call(monkeypatch: Any) -> None:
    built: list[FakeModels] = []

    def build() -> FakeModels:
        built.append(FakeModels())
        return built[-1]

    monkeypatch.setattr(runtime, "_models", None)
    monkeypatch.setattr(runtime, "_build_models", build)

    service = EmbeddingService()
    assert built == []
    assert service.dense_model_name == get_settings().EMBEDDING_MODEL


def test_ask_paths_never_import_gliner() -> None:
    assert not hasattr(history_service, "get_gliner_extractor")
    assert not hasattr(threads_module, "get_gliner_extractor")

    entities = SimpleNamespace(entities=["heuristic-entity"])
    original = history_service.EntityRelationExtractor.extract_from_text
    history_service.EntityRelationExtractor.extract_from_text = classmethod(  # type: ignore[assignment]
        lambda cls, text: entities
    )
    try:
        assert history_service._extract_entities("anything") == ["heuristic-entity"]
    finally:
        history_service.EntityRelationExtractor.extract_from_text = original  # type: ignore[assignment]


class FakeEntityIndex:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def search_similar(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(kwargs)
        if kwargs["name"] == "Alice Chen":
            return [
                {
                    "entity_id": "ent_alice",
                    "name": "Alice Chen",
                    "entity_type": "PERSON",
                    "_score": 0.91,
                }
            ]
        return []

    async def close(self) -> None:
        self.closed = True


@pytest.mark.anyio
async def test_entity_seed_search_uses_heuristic_query_entities() -> None:
    index = FakeEntityIndex()
    retriever = GraphRetriever(driver=SimpleNamespace(), entity_index=index)

    seeds = await retriever.search_entity_seeds(
        "Alice Chen leads PostgreSQL",
        top_k=5,
        filter_criteria=RetrievalFilter(owner_user_id="usr_alice_01"),
    )

    assert [seed["entity_id"] for seed in seeds] == ["ent_alice"]
    assert [seed["_seed"] for seed in seeds] == ["Alice Chen"]
    assert index.calls[0]["owner_user_id"] == "usr_alice_01"
    assert index.closed is False


@pytest.mark.anyio
async def test_ask_budget_caps_the_whole_run(monkeypatch: Any) -> None:
    monkeypatch.setattr(get_settings(), "ASK_TOTAL_BUDGET_SECONDS", 0.01)

    async def slow() -> str:
        await asyncio.sleep(1.0)
        return "too late"

    with pytest.raises(AskBudgetExceededError, match="0.01s budget"):
        await run_with_ask_budget(slow())


@pytest.mark.anyio
async def test_litellm_uses_one_retry_and_thirty_second_timeout(monkeypatch: Any) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_CACHE_ENABLED", False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    calls: list[dict[str, Any]] = []
    attempts = 0

    async def fake_acompletion(**kwargs: Any) -> Any:
        nonlocal attempts
        attempts += 1
        calls.append(kwargs)
        if attempts == 1:
            raise RuntimeError("429 rate limit")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(gateway_module.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(gateway_module.litellm, "completion_cost", lambda **kwargs: 0.0001)
    monkeypatch.setattr(gateway_module.asyncio, "sleep", no_sleep)

    gateway = ModelGateway()
    response = await gateway.complete(prompt="hello")

    assert response.content == "ok"
    assert attempts == 2
    assert all(call["num_retries"] == 1 for call in calls)
    assert all(call["timeout"] == 30.0 for call in calls)
