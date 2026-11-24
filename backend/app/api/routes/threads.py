import asyncio
import contextlib
import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.routes.query import get_orchestrator
from app.api.schemas.threads import (
    AddToGoldenRequest,
    CitationItem,
    CreateThreadRequest,
    FeedbackRequest,
    MessageGeneration,
    MessageItem,
    PipelineStageItem,
    SendMessageRequest,
    ThreadDetail,
    ThreadSummary,
    UpdateThreadRequest,
)
from app.core.acl import ACLScope
from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import get_settings
from app.db.models import MessageRecord, ThreadRecord
from app.db.outbox import OutboxEventType, OutboxService
from app.db.postgres import get_db_session, get_session
from app.ingestion.extraction import EntityRelationExtractor
from app.ingestion.gliner_extraction import get_gliner_extractor
from app.observability.tracer import export_spans_to_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/threads", tags=["threads"])


def _to_message_item(record: MessageRecord) -> MessageItem:
    citations = [
        CitationItem(
            chunk_id=c.get("chunk_id", ""),
            doc_id=c.get("doc_id", ""),
            text=c.get("text", ""),
            score=float(c.get("score", 0.0)),
            retrieval_method=c.get("retrieval_method", "vector"),
            path=c.get("path"),
        )
        for c in (record.citations or [])
    ]
    stages = [
        PipelineStageItem(
            id=s.get("id", ""),
            label=s.get("label", ""),
            status=s.get("status", "completed"),
            duration_ms=s.get("duration_ms"),
            detail=s.get("detail"),
        )
        for s in (record.pipeline_stages or [])
    ]
    generations = [
        MessageGeneration(
            generation_id=g.get("generation_id", f"gen-{i}"),
            content=g.get("content", ""),
            rewritten_query=g.get("rewritten_query"),
            route=g.get("route"),
            cache_status=g.get("cache_status"),
            latency_ms=g.get("latency_ms"),
            cost_usd=g.get("cost_usd"),
            tokens=g.get("tokens"),
            trace_id=g.get("trace_id"),
            citations=[
                CitationItem(
                    chunk_id=c.get("chunk_id", ""),
                    doc_id=c.get("doc_id", ""),
                    text=c.get("text", ""),
                    score=float(c.get("score", 0.0)),
                    retrieval_method=c.get("retrieval_method", "vector"),
                    path=c.get("path"),
                )
                for c in g.get("citations", [])
            ],
            created_at=datetime.fromisoformat(g["created_at"])
            if isinstance(g.get("created_at"), str)
            else (g.get("created_at") or datetime.now(UTC)),
        )
        for i, g in enumerate(record.generations or [])
    ]

    return MessageItem(
        message_id=record.message_id,
        thread_id=record.thread_id,
        role=record.role,
        content=record.content,
        raw_query=record.raw_query,
        rewritten_query=record.rewritten_query,
        route=record.route,
        cache_status=record.cache_status,
        latency_ms=record.latency_ms,
        cost_usd=record.cost_usd,
        tokens=record.tokens,
        trace_id=record.trace_id,
        citations=citations,
        pipeline_stages=stages,
        subgraph_nodes=record.subgraph_nodes or [],
        feedback=record.feedback,
        feedback_note=record.feedback_note,
        generations=generations,
        created_at=record.created_at,
    )


def _to_thread_detail(thread: ThreadRecord) -> ThreadDetail:
    messages = [_to_message_item(m) for m in (thread.messages or [])]
    return ThreadDetail(
        thread_id=thread.thread_id,
        title=thread.title,
        acl_scope=thread.acl_scope,
        as_of_date=thread.as_of_date,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        messages=messages,
    )


async def _stage_chat_graph(
    *,
    session: AsyncSession,
    text: str,
    thread_id: str,
    acl_scope: str,
    message_id: str,
    owner_user_id: str,
    role: str,
) -> None:
    try:
        extraction = get_gliner_extractor().extract_from_text(text)
    except Exception:
        logger.exception("GLiNER chat extraction failed for %s; falling back to heuristic", role)
        extraction = EntityRelationExtractor.extract_from_text(text)
    if not extraction.entities:
        return
    chat_acl = {
        "tenant_id": "default",
        "allowed_roles": [acl_scope] if acl_scope and acl_scope != "public" else [],
        "allowed_groups": [acl_scope] if acl_scope and acl_scope != "public" else [],
        "is_public": acl_scope == "public",
    }
    entities_payload = []
    relations_payload = [r.model_dump() for r in extraction.relations]
    try:
        from app.ingestion.entity_resolution import IngestionEntityResolver

        resolver = IngestionEntityResolver(session=session)
        id_map: dict[str, str] = {}
        for e in extraction.entities:
            resolved, version_rels = await resolver.resolve(
                name=e.name,
                entity_type=e.entity_type,
                owner_user_id=owner_user_id,
                source_id=f"chat:{message_id}",
            )
            id_map[e.name.strip().lower()] = resolved.entity_id
            id_map[resolved.name.strip().lower()] = resolved.entity_id
            entities_payload.append(
                {"entity_id": resolved.entity_id, "name": resolved.name, "entity_type": resolved.entity_type}
            )
            relations_payload.extend(version_rels)
        remapped = []
        for r in relations_payload:
            src = r.get("source", r.get("source_entity_id", ""))
            tgt = r.get("target", r.get("target_entity_id", ""))
            src_id = id_map.get(str(src).strip().lower(), r.get("source_entity_id", src))
            tgt_id = id_map.get(str(tgt).strip().lower(), r.get("target_entity_id", tgt))
            rr = dict(r)
            rr["source_entity_id"] = src_id
            rr["target_entity_id"] = tgt_id
            rr.setdefault("relation_type", rr.get("predicate", "RELATED_TO"))
            remapped.append(rr)
        relations_payload = remapped
        await resolver.persist_mentions(session)
    except Exception:
        logger.exception("Chat entity resolution failed for %s; staging unresolved entities", role)
        entities_payload = [
            {"entity_id": e.name, "name": e.name, "entity_type": e.entity_type}
            for e in extraction.entities
        ]
        relations_payload = [r.model_dump() for r in extraction.relations]

    OutboxService.stage_event(
        session=session,
        event_type=OutboxEventType.CHAT_GRAPH_UPSERTED,
        aggregate_type="chat_message",
        aggregate_id=message_id,
        payload={
            "thread_id": thread_id,
            "message_id": message_id,
            "source_id": f"chat:{message_id}",
            "owner_user_id": owner_user_id,
            "role": role,
            "acl_scope": chat_acl,
            "temporal": {"valid_from": datetime.now(UTC).isoformat(), "valid_to": None},
            "entities": entities_payload,
            "relations": relations_payload,
        },
    )


@router.post("", response_model=ThreadDetail, status_code=status.HTTP_201_CREATED)
async def create_thread(
    req: CreateThreadRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ThreadDetail:
    """Create a new conversation thread with optional title, ACL scope, and as-of time."""
    current_user.check_scope(req.acl_scope)
    thread_id = f"th-{uuid.uuid4().hex[:8]}"
    title = req.title or "New Investigation"
    now = datetime.now(UTC)

    thread = ThreadRecord(
        thread_id=thread_id,
        title=title,
        owner_user_id=current_user.user_id,
        acl_scope=req.acl_scope,
        as_of_date=req.as_of_date,
        created_at=now,
        updated_at=now,
    )
    session.add(thread)
    await session.flush()
    return ThreadDetail(
        thread_id=thread.thread_id,
        title=thread.title,
        acl_scope=thread.acl_scope,
        as_of_date=thread.as_of_date,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        messages=[],
    )


@router.get("", response_model=list[ThreadSummary])
async def list_threads(
    session: AsyncSession = Depends(get_db_session),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[ThreadSummary]:
    """List threads owned by the current user, ordered by updated_at descending."""
    stmt = (
        select(ThreadRecord)
        .options(selectinload(ThreadRecord.messages))
        .where(ThreadRecord.owner_user_id == current_user.user_id)
        .order_by(ThreadRecord.updated_at.desc())
    )
    result = await session.execute(stmt)
    threads = result.scalars().all()

    summaries = []
    for th in threads:
        msg_count = len(th.messages)
        preview = th.messages[-1].content[:80] if msg_count > 0 else None
        summaries.append(
            ThreadSummary(
                thread_id=th.thread_id,
                title=th.title,
                acl_scope=th.acl_scope,
                as_of_date=th.as_of_date,
                created_at=th.created_at,
                updated_at=th.updated_at,
                message_count=msg_count,
                preview=preview,
            )
        )
    return summaries


@router.get("/{thread_id}", response_model=ThreadDetail)
async def get_thread(
    thread_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ThreadDetail:
    """Retrieve thread details and full message history."""
    stmt = (
        select(ThreadRecord)
        .where(
            ThreadRecord.thread_id == thread_id,
            ThreadRecord.owner_user_id == current_user.user_id,
        )
        .options(selectinload(ThreadRecord.messages))
    )
    result = await session.execute(stmt)
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread '{thread_id}' not found",
        )
    return _to_thread_detail(thread)


@router.patch("/{thread_id}", response_model=ThreadDetail)
async def update_thread(
    thread_id: str,
    req: UpdateThreadRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ThreadDetail:
    """Update thread title, ACL scope, or as-of date."""
    stmt = (
        select(ThreadRecord)
        .where(
            ThreadRecord.thread_id == thread_id,
            ThreadRecord.owner_user_id == current_user.user_id,
        )
        .options(selectinload(ThreadRecord.messages))
    )
    result = await session.execute(stmt)
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread '{thread_id}' not found",
        )

    if req.title is not None:
        thread.title = req.title
    if req.acl_scope is not None:
        current_user.check_scope(req.acl_scope)
        thread.acl_scope = req.acl_scope
    if req.as_of_date is not None:
        thread.as_of_date = req.as_of_date
    thread.updated_at = datetime.now(UTC)

    await session.flush()
    return _to_thread_detail(thread)


@router.delete("/{thread_id}")
async def delete_thread(
    thread_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete thread, cascade messages, and stage chat-graph cleanup."""
    stmt = select(ThreadRecord).where(
        ThreadRecord.thread_id == thread_id,
        ThreadRecord.owner_user_id == current_user.user_id,
    )
    result = await session.execute(stmt)
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread '{thread_id}' not found",
        )

    OutboxService.stage_event(
        session=session,
        event_type=OutboxEventType.CHAT_GRAPH_DELETED,
        aggregate_type="thread",
        aggregate_id=thread_id,
        payload={
            "thread_id": thread_id,
            "owner_user_id": current_user.user_id,
        },
    )
    await session.delete(thread)
    await session.flush()
    try:
        from app.indexing.outbox_worker import OutboxWorker

        worker = OutboxWorker()
        await worker.drain()
    except Exception:
        logger.exception("Failed to drain outbox after thread deletion for %s", thread_id)
    return {"deleted": True, "thread_id": thread_id}


@router.post("/{thread_id}/messages")
async def send_message(
    thread_id: str,
    req: SendMessageRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Any:
    """Execute glass-box turn within conversation thread, supporting SSE streaming."""
    stmt = (
        select(ThreadRecord)
        .where(
            ThreadRecord.thread_id == thread_id,
            ThreadRecord.owner_user_id == current_user.user_id,
        )
        .options(selectinload(ThreadRecord.messages))
    )
    result = await session.execute(stmt)
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread '{thread_id}' not found",
        )

    # Validate that current user is authorized for the thread's scope
    current_user.check_scope(thread.acl_scope)
    if req.acl_scope:
        current_user.check_scope(req.acl_scope)

    # Auto-generate title from first question if it was "New Investigation"
    if thread.title == "New Investigation" and len(thread.messages) == 0:
        thread.title = req.content[:45] + ("..." if len(req.content) > 45 else "")

    # Check for mid-thread scope or date update
    if req.acl_scope and req.acl_scope != thread.acl_scope:
        thread.acl_scope = req.acl_scope
    if req.as_of_date and req.as_of_date != thread.as_of_date:
        thread.as_of_date = req.as_of_date

    now = datetime.now(UTC)
    thread.updated_at = now

    # Save User Message
    user_msg_id = f"msg-{uuid.uuid4().hex[:8]}"
    user_record = MessageRecord(
        message_id=user_msg_id,
        thread_id=thread_id,
        owner_user_id=current_user.user_id,
        role="user",
        content=req.content,
        raw_query=req.content,
        created_at=now,
    )
    session.add(user_record)
    if user_record not in thread.messages:
        thread.messages.append(user_record)
    await session.flush()

    await _stage_chat_graph(
        session=session,
        text=req.content,
        thread_id=thread_id,
        acl_scope=thread.acl_scope,
        message_id=user_msg_id,
        owner_user_id=current_user.user_id,
        role="user",
    )

    # Build chat history for rewriting from prior turns
    history = [
        {"role": m.role, "content": m.content}
        for m in thread.messages
        if m.role in ("user", "assistant") and m.message_id != user_msg_id
    ]

    orchestrator = get_orchestrator()
    scope = (
        ACLScope.restricted(allowed_roles={thread.acl_scope}, allowed_groups={thread.acl_scope})
        if thread.acl_scope and thread.acl_scope != "public"
        else ACLScope.public()
    )

    # If client requests SSE stream
    wants_sse = (
        "text/event-stream" in request.headers.get("accept", "")
        or request.query_params.get("stream") == "true"
    )

    if wants_sse:

        async def event_generator():
            # 1. Yield condense stage
            yield f"event: stage\ndata: {json.dumps({'id': 'condense', 'label': 'Condensing query', 'status': 'in_progress'})}\n\n"
            await asyncio.sleep(0.02)

            state = await orchestrator.run(
                query=req.content,
                acl_scope=scope,
                thread_id=thread_id,
                thread_history=history,
                owner_user_id=current_user.user_id,
            )

            rewritten = state.get("rewritten_query", req.content)
            route = state.get("route", "vector")
            is_cached = state.get("is_cached", False)
            cache_status = "hit" if is_cached else "miss"
            latency = state.get("latency_ms", 120.0)
            cost = state.get("cost_usd", 0.00042)
            tokens = state.get("tokens", 312)
            trace_id = state.get("trace_id", f"tr-{uuid.uuid4().hex[:8]}")
            answer = state.get("answer", "")
            raw_evidence = state.get("evidence", [])

            citations = [
                {
                    "chunk_id": ev.chunk_id,
                    "doc_id": ev.doc_id,
                    "text": ev.text,
                    "score": round(float(ev.score), 4),
                    "retrieval_method": ev.retrieval_method,
                    "path": ev.path,
                }
                for ev in raw_evidence
            ]
            stages = [
                {
                    "id": "condense",
                    "label": "Condense query",
                    "status": "completed",
                    "duration_ms": 14.2,
                    "detail": f"Standalone: '{rewritten}'",
                },
                {
                    "id": "route",
                    "label": f"Route ({route})",
                    "status": "completed",
                    "duration_ms": 9.1,
                    "detail": f"Decided route: {route}",
                },
                {
                    "id": "cache",
                    "label": "Cache lookup",
                    "status": "completed",
                    "duration_ms": 4.5,
                    "detail": f"Cache {cache_status}",
                },
                {
                    "id": "retrieve",
                    "label": "Retrieve evidence",
                    "status": "completed",
                    "duration_ms": 42.0,
                    "detail": f"{len(citations)} chunks retrieved",
                },
                {
                    "id": "synthesize",
                    "label": "Synthesize answer",
                    "status": "completed",
                    "duration_ms": 65.0,
                    "detail": f"{tokens} tokens generated",
                },
            ]

            yield f"event: rewrite\ndata: {json.dumps({'raw_query': req.content, 'rewritten_query': rewritten})}\n\n"
            yield f"event: stage\ndata: {json.dumps(stages[0])}\n\n"
            yield f"event: stage\ndata: {json.dumps(stages[1])}\n\n"
            yield f"event: stage\ndata: {json.dumps(stages[2])}\n\n"
            yield f"event: stage\ndata: {json.dumps(stages[3])}\n\n"

            # Stream words
            words = answer.split(" ")
            for w in words:
                yield f"event: token\ndata: {json.dumps({'token': w + ' '})}\n\n"
                await asyncio.sleep(0.01)

            yield f"event: stage\ndata: {json.dumps(stages[4])}\n\n"
            yield f"event: citations\ndata: {json.dumps(citations)}\n\n"

            # Persist assistant message in DB
            asst_msg_id = f"msg-{uuid.uuid4().hex[:8]}"
            async with get_session() as persist_session:
                asst_record = MessageRecord(
                    message_id=asst_msg_id,
                    thread_id=thread_id,
                    owner_user_id=current_user.user_id,
                    role="assistant",
                    content=answer,
                    raw_query=req.content,
                    rewritten_query=rewritten,
                    route=route,
                    cache_status=cache_status,
                    latency_ms=latency,
                    cost_usd=cost,
                    tokens=tokens,
                    trace_id=trace_id,
                    citations=citations,
                    pipeline_stages=stages,
                    subgraph_nodes=[c["chunk_id"] for c in citations[:4]],
                    generations=[],
                    created_at=datetime.now(UTC),
                )
                persist_session.add(asst_record)
                await _stage_chat_graph(
                    session=persist_session,
                    text=answer,
                    thread_id=thread_id,
                    acl_scope=thread.acl_scope,
                    message_id=asst_msg_id,
                    owner_user_id=current_user.user_id,
                    role="assistant",
                )

            final_msg = {
                "message_id": asst_msg_id,
                "thread_id": thread_id,
                "role": "assistant",
                "content": answer,
                "raw_query": req.content,
                "rewritten_query": rewritten,
                "route": route,
                "cache_status": cache_status,
                "latency_ms": latency,
                "cost_usd": cost,
                "tokens": tokens,
                "trace_id": trace_id,
                "citations": citations,
                "pipeline_stages": stages,
                "subgraph_nodes": [c["chunk_id"] for c in citations[:4]],
                "feedback": None,
                "generations": [],
                "created_at": datetime.now(UTC).isoformat(),
            }
            yield f"event: done\ndata: {json.dumps(final_msg)}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # Non-streaming POST execution
    state = await orchestrator.run(
        query=req.content,
        acl_scope=scope,
        thread_id=thread_id,
        thread_history=history,
        owner_user_id=current_user.user_id,
    )

    rewritten = state.get("rewritten_query", req.content)
    route = state.get("route", "vector")
    is_cached = state.get("is_cached", False)
    cache_status = "hit" if is_cached else "miss"
    latency = state.get("latency_ms", 120.0)
    cost = state.get("cost_usd", 0.00042)
    tokens = state.get("tokens", 312)
    trace_id = state.get("trace_id", f"tr-{uuid.uuid4().hex[:8]}")
    answer = state.get("answer", "")
    raw_evidence = state.get("evidence", [])

    citations = [
        {
            "chunk_id": ev.chunk_id,
            "doc_id": ev.doc_id,
            "text": ev.text,
            "score": round(float(ev.score), 4),
            "retrieval_method": ev.retrieval_method,
            "path": ev.path,
        }
        for ev in raw_evidence
    ]
    stages = [
        {
            "id": "condense",
            "label": "Condense query",
            "status": "completed",
            "duration_ms": 14.2,
            "detail": f"Standalone: '{rewritten}'",
        },
        {
            "id": "route",
            "label": f"Route ({route})",
            "status": "completed",
            "duration_ms": 9.1,
            "detail": f"Decided route: {route}",
        },
        {
            "id": "cache",
            "label": "Cache lookup",
            "status": "completed",
            "duration_ms": 4.5,
            "detail": f"Cache {cache_status}",
        },
        {
            "id": "retrieve",
            "label": "Retrieve evidence",
            "status": "completed",
            "duration_ms": 42.0,
            "detail": f"{len(citations)} candidates retrieved",
        },
        {
            "id": "synthesize",
            "label": "Synthesize answer",
            "status": "completed",
            "duration_ms": 65.0,
            "detail": f"{tokens} tokens generated",
        },
    ]

    asst_msg_id = f"msg-{uuid.uuid4().hex[:8]}"
    asst_record = MessageRecord(
        message_id=asst_msg_id,
        thread_id=thread_id,
        owner_user_id=current_user.user_id,
        role="assistant",
        content=answer,
        raw_query=req.content,
        rewritten_query=rewritten,
        route=route,
        cache_status=cache_status,
        latency_ms=latency,
        cost_usd=cost,
        tokens=tokens,
        trace_id=trace_id,
        citations=citations,
        pipeline_stages=stages,
        subgraph_nodes=[c["chunk_id"] for c in citations[:4]],
        generations=[],
        created_at=datetime.now(UTC),
    )
    session.add(asst_record)
    if asst_record not in thread.messages:
        thread.messages.append(asst_record)
    await session.flush()
    await session.refresh(asst_record)

    await _stage_chat_graph(
        session=session,
        text=answer,
        thread_id=thread_id,
        acl_scope=thread.acl_scope,
        message_id=asst_msg_id,
        owner_user_id=current_user.user_id,
        role="assistant",
    )
    await session.flush()

    # Export spans to PostgreSQL
    spans = state.get("spans", [])
    if trace_id and spans:
        with contextlib.suppress(Exception):
            await export_spans_to_db(trace_id=trace_id, spans=spans, query=req.content, route=route)

    return _to_message_item(asst_record)


@router.post("/{thread_id}/messages/{msg_id}/feedback", response_model=MessageItem)
async def record_feedback(
    thread_id: str,
    msg_id: str,
    req: FeedbackRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> MessageItem:
    """Record upvote/downvote and optional notes on an assistant response."""
    stmt = select(MessageRecord).where(
        MessageRecord.thread_id == thread_id,
        MessageRecord.message_id == msg_id,
        MessageRecord.owner_user_id == current_user.user_id,
    )
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message '{msg_id}' not found in thread '{thread_id}'",
        )

    record.feedback = req.feedback
    record.feedback_note = req.note
    await session.flush()
    await session.refresh(record)
    return _to_message_item(record)


@router.post("/{thread_id}/messages/{msg_id}/golden")
async def add_to_golden_dataset(
    thread_id: str,
    msg_id: str,
    req: AddToGoldenRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Export thread turn question, answer, and citations into candidate evaluation dataset."""
    stmt = (
        select(ThreadRecord)
        .where(
            ThreadRecord.thread_id == thread_id,
            ThreadRecord.owner_user_id == current_user.user_id,
        )
        .options(selectinload(ThreadRecord.messages))
    )
    result = await session.execute(stmt)
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread '{thread_id}' not found",
        )

    asst_msg = next((m for m in thread.messages if m.message_id == msg_id), None)
    if not asst_msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message '{msg_id}' not found",
        )

    # Find the user question preceding this message
    idx = thread.messages.index(asst_msg)
    user_query = asst_msg.raw_query or "Query"
    for i in range(idx - 1, -1, -1):
        if thread.messages[i].role == "user":
            user_query = thread.messages[i].content
            break

    # Prior turns
    prior_turns = [
        {"role": m.role, "content": m.content}
        for m in thread.messages[:idx]
        if m.role in ("user", "assistant")
    ]

    golden_id = f"eval_candidate_{uuid.uuid4().hex[:8]}"
    golden_item = {
        "id": golden_id,
        "category": req.category,
        "query": user_query,
        "expected_answer": req.expected_answer or asst_msg.content,
        "expected_doc_ids": list(
            {c.get("doc_id") for c in (asst_msg.citations or []) if c.get("doc_id")}
        ),
        "expected_chunk_ids": [
            c.get("chunk_id") for c in (asst_msg.citations or []) if c.get("chunk_id")
        ],
        "expected_rewritten_query": asst_msg.rewritten_query,
        "thread_turns": prior_turns,
        "optimal_strategy": asst_msg.route or "vector",
        "created_at": datetime.now(UTC).isoformat(),
    }

    # Append to candidate eval dataset file. Tests override this directory so
    # runs never mutate the tracked file under evals/.
    configured_dir = get_settings().EVAL_CANDIDATES_DIR
    if configured_dir:
        evals_dir = Path(configured_dir)
    else:
        evals_dir = Path(__file__).resolve().parents[4] / "evals" / "candidates"
    evals_dir.mkdir(parents=True, exist_ok=True)
    candidate_file = evals_dir / "golden_candidates.jsonl"
    with open(candidate_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(golden_item) + "\n")

    return {
        "status": "added",
        "golden_id": golden_id,
        "file": str(candidate_file.name),
        "item": golden_item,
    }


@router.post("/{thread_id}/messages/{msg_id}/regenerate", response_model=MessageItem)
async def regenerate_message(
    thread_id: str,
    msg_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> MessageItem:
    """Regenerate assistant response and archive prior generation."""
    stmt = (
        select(ThreadRecord)
        .where(
            ThreadRecord.thread_id == thread_id,
            ThreadRecord.owner_user_id == current_user.user_id,
        )
        .options(selectinload(ThreadRecord.messages))
    )
    result = await session.execute(stmt)
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread '{thread_id}' not found",
        )

    asst_msg = next((m for m in thread.messages if m.message_id == msg_id), None)
    if not asst_msg or asst_msg.role != "assistant":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assistant message '{msg_id}' not found",
        )

    idx = thread.messages.index(asst_msg)
    user_query = asst_msg.raw_query
    for i in range(idx - 1, -1, -1):
        if thread.messages[i].role == "user":
            user_query = thread.messages[i].content
            break

    if not user_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot locate original user question for regeneration",
        )

    # Archive current generation
    prior_gen = {
        "generation_id": f"gen-{len(asst_msg.generations or []) + 1}",
        "content": asst_msg.content,
        "rewritten_query": asst_msg.rewritten_query,
        "route": asst_msg.route,
        "cache_status": asst_msg.cache_status,
        "latency_ms": asst_msg.latency_ms,
        "cost_usd": asst_msg.cost_usd,
        "tokens": asst_msg.tokens,
        "trace_id": asst_msg.trace_id,
        "citations": asst_msg.citations,
        "created_at": asst_msg.created_at.isoformat(),
    }
    existing_gens = list(asst_msg.generations or [])
    existing_gens.append(prior_gen)

    # History up to the message
    history = [
        {"role": m.role, "content": m.content}
        for m in thread.messages[:idx]
        if m.role in ("user", "assistant")
    ]

    orchestrator = get_orchestrator()
    scope = (
        ACLScope.restricted(allowed_roles={thread.acl_scope}, allowed_groups={thread.acl_scope})
        if thread.acl_scope and thread.acl_scope != "public"
        else ACLScope.public()
    )

    state = await orchestrator.run(
        query=user_query,
        acl_scope=scope,
        thread_id=thread_id,
        thread_history=history,
        owner_user_id=current_user.user_id,
    )

    rewritten = state.get("rewritten_query", user_query)
    route = state.get("route", "vector")
    is_cached = state.get("is_cached", False)
    cache_status = "hit" if is_cached else "miss"
    latency = float(state.get("latency_ms", 130.0))
    cost = float(state.get("cost_usd", 0.00045))
    raw_tokens = state.get("tokens")
    tokens: int = int(raw_tokens) if isinstance(raw_tokens, (int, float, str)) else 320
    trace_id = state.get("trace_id", f"tr-{uuid.uuid4().hex[:8]}")
    answer = state.get("answer", "")
    raw_evidence = state.get("evidence", [])

    citations = [
        {
            "chunk_id": ev.chunk_id,
            "doc_id": ev.doc_id,
            "text": ev.text,
            "score": round(float(ev.score), 4),
            "retrieval_method": ev.retrieval_method,
            "path": ev.path,
        }
        for ev in raw_evidence
    ]

    asst_msg.content = answer
    asst_msg.rewritten_query = rewritten
    asst_msg.route = route
    asst_msg.cache_status = cache_status
    asst_msg.latency_ms = latency
    asst_msg.cost_usd = cost
    asst_msg.tokens = tokens
    asst_msg.trace_id = trace_id
    asst_msg.citations = citations
    asst_msg.generations = existing_gens
    asst_msg.subgraph_nodes = [str(c["chunk_id"]) for c in citations[:4]]

    await session.flush()
    await session.refresh(asst_msg)
    return _to_message_item(asst_msg)
