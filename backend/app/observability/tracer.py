"""OpenTelemetry tracing for the RAG workflow.

Spans are exported to Langfuse's OTLP HTTP endpoint with Basic auth derived
from the Langfuse public/secret keys. When either key is missing the provider
has no processors, so tracing is a strict no-op and never opens a connection.
"""

from __future__ import annotations

import base64
import inspect
import logging
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from functools import wraps
from typing import Any, TypeVar

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import Settings, get_settings
from app.db.models import SpanRecord
from app.db.postgres import get_session

logger = logging.getLogger(__name__)

TRACER_NAME = "graphrag-lab"
_provider: TracerProvider | None = None

F = TypeVar("F", bound=Callable[..., Coroutine[Any, Any, Any]])


def build_tracer_provider(settings: Settings | None = None) -> TracerProvider:
    """Build a provider exporting to Langfuse only when both keys are configured."""
    settings = settings or get_settings()
    provider = TracerProvider(
        resource=Resource.create({"service.name": "graphrag-intelligence-lab"})
    )
    public_key = settings.LANGFUSE_PUBLIC_KEY
    secret_key = settings.LANGFUSE_SECRET_KEY
    if not (public_key and secret_key):
        logger.info("Langfuse keys unset; OpenTelemetry export disabled")
        return provider

    token = base64.b64encode(f"{public_key}:{secret_key}".encode("utf-8")).decode("ascii")
    endpoint = f"{settings.LANGFUSE_HOST.rstrip('/')}/api/public/otel/v1/traces"
    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        headers={"Authorization": f"Basic {token}"},
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def setup_telemetry() -> trace.Tracer:
    """Register the process-wide provider once and return the workflow tracer."""
    global _provider
    if _provider is None:
        settings = get_settings()
        if settings.APP_ENV == "test":
            # Keep the hermetic suite offline even when .env carries real keys.
            settings = settings.model_copy(
                update={"LANGFUSE_PUBLIC_KEY": None, "LANGFUSE_SECRET_KEY": None}
            )
        _provider = build_tracer_provider(settings)
        trace.set_tracer_provider(_provider)
    return trace.get_tracer(TRACER_NAME)


def get_tracer() -> trace.Tracer:
    """Return the tracer used by workflow nodes and LLM calls."""
    return trace.get_tracer(TRACER_NAME)


def record_llm_usage(span: trace.Span, response: Any) -> None:
    """Attach token counts and LiteLLM completion cost to an LLM span."""
    usage = response.usage
    span.set_attribute("llm.model", str(getattr(response, "model", "unknown")))
    span.set_attribute("llm.input_tokens", int(getattr(usage, "prompt_tokens", 0)))
    span.set_attribute("llm.output_tokens", int(getattr(usage, "completion_tokens", 0)))
    span.set_attribute("llm.total_tokens", int(getattr(usage, "total_tokens", 0)))
    # ModelGateway fills usage.cost_usd from litellm.completion_cost() on the
    # live path (with a local pricing fallback when the map is unavailable).
    span.set_attribute("llm.completion_cost_usd", float(getattr(usage, "cost_usd", 0.0)))
    span.set_attribute("llm.cached", bool(getattr(response, "cached", False)))


def traced_node(name: str, fn: F) -> F:
    """Wrap a LangGraph node in exactly one OTel span (sync or async)."""
    span_name = f"langgraph.{name}"

    if inspect.iscoroutinefunction(fn):

        @wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            with get_tracer().start_as_current_span(span_name) as span:
                span.set_attribute("langgraph.node", name)
                return await fn(*args, **kwargs)

        return async_wrapper  # type: ignore[return-value]

    @wraps(fn)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        with get_tracer().start_as_current_span(span_name) as span:
            span.set_attribute("langgraph.node", name)
            return fn(*args, **kwargs)

    return sync_wrapper  # type: ignore[return-value]


async def export_spans_to_db(
    trace_id: str,
    spans: list[dict[str, Any]],
    query: str = "",
    route: str = "",
) -> None:
    """Store the workflow's diagnostic spans in the PostgreSQL spans table."""
    now = datetime.now(UTC)
    async with get_session() as session:
        for sp in spans:
            span_id = sp.get("id") or f"sp_{uuid.uuid4().hex[:12]}"
            duration = float(sp.get("duration_ms", 0.0))
            record = SpanRecord(
                span_id=span_id,
                trace_id=trace_id,
                parent_span_id=None,
                name=sp.get("name", "pipeline_step"),
                start_time=now,
                end_time=now,
                duration_ms=duration,
                status_code=sp.get("status", "ok"),
                status_message=sp.get("meta"),
                attributes={
                    "service": sp.get("service", "Pipeline"),
                    "start_ms": sp.get("start_ms", 0.0),
                    "meta": sp.get("meta", ""),
                    "query": query,
                    "route": route,
                },
                events=[],
            )
            session.add(record)
