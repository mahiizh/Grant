"""Step 6: one OTel span per LangGraph node, exported only to configured Langfuse."""

import base64
from typing import Any, cast

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExportResult,
    SpanExporter,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core.config import get_settings
from app.observability import tracer as telemetry
from app.orchestration.workflow import RAGOrchestrator
from app.web_grounding.web import WebPage
from tests.fakes.fake_gateway import FakeModelGateway
from tests.fakes.fake_web import FakeWebClient, FakeWebIngestor
from tests.unit.test_slice2_web_grounding import (
    EmptyGraphRetriever,
    EmptyHybridRetriever,
    EvidenceHybridRetriever,
    FakeHistory,
    build_orchestrator,
)

WEB_PAGE = WebPage(
    url="https://example.com/tracing",
    title="Tracing source",
    text="The incident timeline describes detection and containment steps.",
    fetched_at="2026-11-26T00:00:00Z",
)


class _CapturingExporter(SpanExporter):
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.exported: list[Any] = []

    def export(self, spans: Any) -> SpanExportResult:
        self.exported.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def _settings(**updates: Any) -> Any:
    return get_settings().model_copy(update=updates)


def _provider_with_memory_exporter() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def _run(
    orchestrator: RAGOrchestrator,
    policy: str,
    *,
    thread_history: list[dict[str, Any]] | None = None,
) -> None:
    import asyncio

    asyncio.run(
        orchestrator.run(
            query="What happened in the incident timeline?",
            answer_policy=cast(Any, policy),
            thread_history=thread_history,
            owner_user_id="usr_alice_01",
        )
    )


@pytest.mark.parametrize("public_key,secret_key", [(None, None), ("pk-only", None), (None, "sk-only")])
def test_no_exporter_created_when_langfuse_keys_unset(
    monkeypatch: pytest.MonkeyPatch, public_key: str | None, secret_key: str | None
) -> None:
    def _forbidden(**kwargs: Any) -> None:
        pytest.fail("OTLPSpanExporter must not be created without both Langfuse keys")

    monkeypatch.setattr(telemetry, "OTLPSpanExporter", _forbidden)
    provider = telemetry.build_tracer_provider(
        _settings(
            LANGFUSE_PUBLIC_KEY=public_key,
            LANGFUSE_SECRET_KEY=secret_key,
        )
    )
    processors = provider._active_span_processor._span_processors  # type: ignore[attr-defined]
    assert processors == ()


def test_langfuse_endpoint_and_basic_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def _exporter(**kwargs: Any) -> _CapturingExporter:
        captured.update(kwargs)
        return _CapturingExporter(**kwargs)

    monkeypatch.setattr(telemetry, "OTLPSpanExporter", _exporter)
    provider = telemetry.build_tracer_provider(
        _settings(
            LANGFUSE_PUBLIC_KEY="pk-test",
            LANGFUSE_SECRET_KEY="sk-test",
            LANGFUSE_HOST="https://cloud.langfuse.com/",
        )
    )
    assert captured["endpoint"] == "https://cloud.langfuse.com/api/public/otel/v1/traces"
    encoded = captured["headers"]["Authorization"].removeprefix("Basic ")
    assert base64.b64decode(encoded).decode("utf-8") == "pk-test:sk-test"
    processors = provider._active_span_processor._span_processors  # type: ignore[attr-defined]
    assert len(processors) == 1
    provider.shutdown()


def test_docs_path_emits_node_and_llm_spans(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, exporter = _provider_with_memory_exporter()
    monkeypatch.setattr(telemetry, "get_tracer", lambda: provider.get_tracer(telemetry.TRACER_NAME))
    orchestrator = build_orchestrator(
        history=FakeHistory(),
        hybrid=EvidenceHybridRetriever(),
        gateway=FakeModelGateway(),
        record_history=True,
    )
    _run(orchestrator, "grounded_only")

    by_name = {span.name: span for span in exporter.get_finished_spans()}
    for node in ("condense_step", "route_step", "cache_step", "retrieve_step", "generate_step"):
        assert f"langgraph.{node}" in by_name
        assert by_name[f"langgraph.{node}"].attributes["langgraph.node"] == node
    llm_span = by_name["llm.completion"]
    assert llm_span.attributes["llm.input_tokens"] > 0
    assert llm_span.attributes["llm.output_tokens"] > 0
    assert llm_span.attributes["llm.total_tokens"] > 0
    assert llm_span.attributes["llm.completion_cost_usd"] > 0.0
    assert llm_span.attributes["llm.model"]
    provider.shutdown()


def test_web_and_abstain_nodes_emit_spans(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, exporter = _provider_with_memory_exporter()
    monkeypatch.setattr(telemetry, "get_tracer", lambda: provider.get_tracer(telemetry.TRACER_NAME))

    web_orch = build_orchestrator(
        history=FakeHistory(),
        hybrid=EmptyHybridRetriever(),
        gateway=FakeModelGateway(),
        web_client=FakeWebClient(pages=[WEB_PAGE]),
        web_ingestor=FakeWebIngestor(),
    )
    _run(web_orch, "grounded_plus_web")
    assert "langgraph.web_step" in {s.name for s in exporter.get_finished_spans()}

    exporter.clear()
    abstain_orch = build_orchestrator(
        history=FakeHistory(),
        hybrid=EmptyHybridRetriever(),
        gateway=FakeModelGateway(),
    )
    _run(abstain_orch, "grounded_only")
    assert "langgraph.abstain_step" in {s.name for s in exporter.get_finished_spans()}
    provider.shutdown()


def test_llm_rewrite_span_carries_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, exporter = _provider_with_memory_exporter()
    monkeypatch.setattr(telemetry, "get_tracer", lambda: provider.get_tracer(telemetry.TRACER_NAME))
    gateway = FakeModelGateway()
    # A non-mock model name makes condense_query take its LLM rewrite branch;
    # with APP_ENV=test the gateway still answers locally without a network call.
    gateway.default_model = "rewrite-test-model"
    orchestrator = build_orchestrator(
        history=FakeHistory(),
        hybrid=EvidenceHybridRetriever(),
        gateway=gateway,
    )
    _run(
        orchestrator,
        "grounded_only",
        thread_history=[
            {"role": "user", "content": "Why did the outbox service fail?"},
            {"role": "assistant", "content": "It failed to sync state to PostgreSQL."},
        ],
    )
    llm_spans = [s for s in exporter.get_finished_spans() if s.name == "llm.completion"]
    assert len(llm_spans) >= 2  # condense rewrite + answer generation
    assert all(s.attributes["llm.output_tokens"] > 0 for s in llm_spans)
    provider.shutdown()


def test_fake_gateway_is_still_usable_for_traced_runs() -> None:
    """Guard that tracing helpers accept the hermetic gateway's ModelResponse."""
    import asyncio

    response = asyncio.run(FakeModelGateway().complete(prompt="hello", mock_response="world"))
    assert isinstance(response.usage.prompt_tokens, int)
    assert response.usage.cost_usd >= 0.0
