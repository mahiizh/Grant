import logging

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.schemas.traces import SpanRecord as APISpanRecord
from app.api.schemas.traces import TraceDetail, TracesResponse, TraceSummary
from app.db.models import MessageRecord
from app.db.models import SpanRecord as DBSpanRecord
from app.db.postgres import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("", response_model=TracesResponse)
async def list_traces(
    route: str | None = Query(None),
    min_latency: int | None = Query(None),
    trace_status: str | None = Query(None, alias="status"),
) -> TracesResponse:
    """List execution traces from PostgreSQL."""
    async with get_session() as session:
        # First query messages that have trace_id
        stmt = (
            select(MessageRecord)
            .where(MessageRecord.trace_id.isnot(None))
            .order_by(MessageRecord.created_at.desc())
            .limit(50)
        )
        msg_result = await session.execute(stmt)
        messages = list(msg_result.scalars().all())

        # Also query spans table directly
        spans_stmt = select(DBSpanRecord).order_by(DBSpanRecord.created_at.desc()).limit(100)
        spans_res = await session.execute(spans_stmt)
        all_spans = list(spans_res.scalars().all())

    # Map trace_id -> spans
    spans_by_trace: dict[str, list[DBSpanRecord]] = {}
    for s in all_spans:
        spans_by_trace.setdefault(s.trace_id, []).append(s)

    trace_summaries: list[TraceSummary] = []

    # Build from messages
    seen_trace_ids = set()
    for m in messages:
        t_id = m.trace_id or ""
        seen_trace_ids.add(t_id)
        trace_summaries.append(
            TraceSummary(
                id=t_id,
                query=m.raw_query or m.content[:80],
                route=m.route or "vector",
                latency_ms=int(m.latency_ms or 0),
                status="ok" if m.content else "error",
                timestamp=m.created_at.isoformat(),
                tokens=m.tokens or 0,
                cost_usd=float(m.cost_usd or 0.0),
                cached=m.cache_status == "hit",
            )
        )

    # Build from any remaining spans not linked to messages
    for t_id, s_list in spans_by_trace.items():
        if t_id in seen_trace_ids or not s_list:
            continue
        first_span = s_list[0]
        total_dur = sum(s.duration_ms for s in s_list)
        meta = first_span.attributes or {}
        trace_summaries.append(
            TraceSummary(
                id=t_id,
                query=meta.get("query", "Pipeline run"),
                route=meta.get("route", "hybrid"),
                latency_ms=int(total_dur),
                status=first_span.status_code or "ok",
                timestamp=first_span.created_at.isoformat(),
                tokens=120,
                cost_usd=0.00003,
                cached=False,
            )
        )

    # Apply filters
    filtered = trace_summaries
    if route:
        filtered = [t for t in filtered if t.route.lower() == route.lower()]
    if min_latency is not None:
        filtered = [t for t in filtered if t.latency_ms >= min_latency]
    if trace_status:
        filtered = [t for t in filtered if t.status.lower() == trace_status.lower()]

    return TracesResponse(traces=filtered, total=len(filtered))


@router.get("/{trace_id}", response_model=TraceDetail)
async def get_trace(trace_id: str) -> TraceDetail:
    """Retrieve full trace waterfall and span metadata from PostgreSQL."""
    async with get_session() as session:
        # Fetch spans
        spans_stmt = (
            select(DBSpanRecord)
            .where(DBSpanRecord.trace_id == trace_id)
            .order_by(DBSpanRecord.start_time.asc())
        )
        spans_res = await session.execute(spans_stmt)
        db_spans = list(spans_res.scalars().all())

        # Fetch message if present
        msg_stmt = select(MessageRecord).where(MessageRecord.trace_id == trace_id)
        msg_res = await session.execute(msg_stmt)
        msg = msg_res.scalar_one_or_none()

    if not db_spans and not msg:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found.")

    api_spans: list[APISpanRecord] = []
    for s in db_spans:
        attrs = s.attributes or {}
        api_spans.append(
            APISpanRecord(
                name=s.name,
                service=attrs.get("service", "Pipeline"),
                start_ms=int(attrs.get("start_ms", 0.0)),
                duration_ms=int(s.duration_ms),
                status=s.status_code or "ok",
                meta=s.status_message or attrs.get("meta", ""),
            )
        )

    query = (msg.raw_query if msg else None) or (
        db_spans[0].attributes.get("query") if db_spans else "Query"
    )
    route = (msg.route if msg else None) or (
        db_spans[0].attributes.get("route") if db_spans else "vector"
    )
    latency = int(
        msg.latency_ms if msg and msg.latency_ms else sum(s.duration_ms for s in db_spans)
    )
    timestamp = (msg.created_at if msg else db_spans[0].created_at).isoformat()
    answer = msg.content if msg else ""
    tokens = msg.tokens if msg and msg.tokens else 100
    cost = float(msg.cost_usd if msg and msg.cost_usd else 0.0)

    chunk_ids = []
    if msg and msg.citations:
        chunk_ids = [c.get("chunk_id", "") for c in msg.citations if "chunk_id" in c]

    return TraceDetail(
        id=trace_id,
        query=query,
        route=route,
        latency_ms=latency,
        status="ok",
        timestamp=timestamp,
        tokens=tokens,
        cost_usd=cost,
        spans=api_spans,
        inputs={"query": query},
        retrieved_chunk_ids=chunk_ids,
        answer=answer,
    )
