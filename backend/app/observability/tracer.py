import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import get_settings
from app.db.models import SpanRecord
from app.db.postgres import get_session

logger = logging.getLogger(__name__)

# Initialize OTel TracerProvider
_provider: TracerProvider | None = None


def setup_telemetry() -> trace.Tracer:
    """Initialize OpenTelemetry tracer with OTLP HTTP exporter."""
    global _provider
    if _provider is None:
        settings = get_settings()
        resource = Resource.create({"service.name": "graphrag-intelligence-lab"})
        _provider = TracerProvider(resource=resource)

        if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
            try:
                otlp_exporter = OTLPSpanExporter(
                    endpoint=f"{settings.OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces"
                )
                _provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            except Exception as e:
                logger.debug("OTLP exporter could not be configured: %s", e)

        trace.set_tracer_provider(_provider)

    return trace.get_tracer("graphrag-lab")


async def export_spans_to_db(
    trace_id: str,
    spans: list[dict[str, Any]],
    query: str = "",
    route: str = "",
) -> None:
    """Store generated trace spans in the PostgreSQL spans table."""
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
