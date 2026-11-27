import asyncio
import contextlib
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.api.routes.query import _sse, get_orchestrator
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
from app.observability.tracer import export_spans_to_db
from app.orchestration.answer_metadata import build_answer_metadata
from app.orchestration.budget import AskBudgetExceededError, run_with_ask_budget

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/threads", tags=["threads"])


def _to_message_item(record: MessageRecord) -> MessageItem:
    metadata = dict(getattr(record, "answer_metadata", None) or {})
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
            source_kind=g.get("source_kind", "docs"),
            source=str(g.get("source") or metadata.get("source") or "docs"),
            answer_path=list(g.get("answer_path") or metadata.get("answer_path") or []),
            top_score=float(g.get("top_score") or metadata.get("top_score") or 0.0),
            stage_timings_ms=dict(
                g.get("stage_timings_ms") or metadata.get("stage_timings_ms") or {}
            ),
            web_sources=list(g.get("web_sources", []) or []),
            query_id=g.get("query_id"),
            answer_id=g.get("answer_id"),
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
        source_kind=getattr(record, "source_kind", "docs") or "docs",
        source=str(metadata.get("source") or "docs"),
        answer_path=list(metadata.get("answer_path") or []),
        top_score=float(metadata.get("top_score") or 0.0),
        stage_timings_ms=dict(metadata.get("stage_timings_ms") or {}),
        web_sources=list(record.web_sources or []),
        query_id=record.query_id,
        answer_id=record.answer_id,
        created_at=record.created_at,
    )


def _thread_acl_scope(thread: ThreadRecord) -> ACLScope:
    """Return the combined owner/shared boundary for a thread."""
    return ACLScope(
        owner_user_id=thread.owner_user_id,
        shared_scope=thread.shared_scope,
    )


def _can_access_thread(thread: ThreadRecord, current_user: AuthenticatedUser) -> bool:
    if current_user.is_admin or thread.owner_user_id == current_user.user_id:
        return True
    return bool(thread.shared_scope and thread.shared_scope in current_user.shared_scopes)


def _ensure_thread_access(thread: ThreadRecord, current_user: AuthenticatedUser) -> None:
    if not _can_access_thread(thread, current_user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")


def _to_thread_detail(thread: ThreadRecord) -> ThreadDetail:
    messages = [_to_message_item(m) for m in (thread.messages or [])]
    return ThreadDetail(
        thread_id=thread.thread_id,
        title=thread.title,
        shared_scope=thread.shared_scope,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        messages=messages,
    )


async def _stage_chat_graph(
    *,
    session: AsyncSession,
    text: str,
    thread_id: str,
    shared_scope: str | None,
    message_id: str,
    owner_user_id: str,
    role: str,
) -> None:
    # Ask/chat paths never load GLiNER; deterministic extraction keeps the
    # request off the heavyweight entity model.
    extraction = EntityRelationExtractor.extract_from_text(text)
    if not extraction.entities:
        return
    chat_acl = {
        "owner_user_id": owner_user_id,
        "shared_scope": shared_scope,
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
            "ingested_at": datetime.now(UTC).isoformat(),
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
    """Create a new owner-private thread, optionally shared to an authorized scope."""
    if req.shared_scope:
        current_user.check_scope(req.shared_scope)
    thread_id = f"th-{uuid.uuid4().hex[:8]}"
    title = req.title or "New Investigation"
    now = datetime.now(UTC)

    thread = ThreadRecord(
        thread_id=thread_id,
        title=title,
        owner_user_id=current_user.user_id,
        shared_scope=req.shared_scope,
        created_at=now,
        updated_at=now,
    )
    session.add(thread)
    await session.flush()
    set_committed_value(thread, "messages", [])
    return _to_thread_detail(thread)


@router.get("", response_model=list[ThreadSummary])
async def list_threads(
    session: AsyncSession = Depends(get_db_session),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[ThreadSummary]:
    """List threads visible to the current user, ordered by updated_at descending."""
    stmt = (
        select(ThreadRecord)
        .options(selectinload(ThreadRecord.messages))
        .order_by(ThreadRecord.updated_at.desc())
    )
    if not current_user.is_admin:
        visibility = ThreadRecord.owner_user_id == current_user.user_id
        if current_user.shared_scopes:
            visibility = or_(
                visibility,
                ThreadRecord.shared_scope.in_(sorted(current_user.shared_scopes)),
            )
        stmt = stmt.where(visibility)
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
                shared_scope=th.shared_scope,
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
        .where(ThreadRecord.thread_id == thread_id)
        .options(selectinload(ThreadRecord.messages))
    )
    result = await session.execute(stmt)
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Thread '{thread_id}' not found")
    _ensure_thread_access(thread, current_user)
    return _to_thread_detail(thread)


@router.patch("/{thread_id}", response_model=ThreadDetail)
async def update_thread(
    thread_id: str,
    req: UpdateThreadRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ThreadDetail:
    """Update thread title or shared scope."""
    stmt = (
        select(ThreadRecord)
        .where(ThreadRecord.thread_id == thread_id)
        .options(selectinload(ThreadRecord.messages))
    )
    result = await session.execute(stmt)
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Thread '{thread_id}' not found")
    _ensure_thread_access(thread, current_user)

    if req.title is not None:
        thread.title = req.title
    if req.shared_scope is not None:
        current_user.check_scope(req.shared_scope)
        thread.shared_scope = req.shared_scope or None
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
    stmt = select(ThreadRecord).where(ThreadRecord.thread_id == thread_id)
    result = await session.execute(stmt)
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Thread '{thread_id}' not found")
    _ensure_thread_access(thread, current_user)

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
        .where(ThreadRecord.thread_id == thread_id)
        .options(selectinload(ThreadRecord.messages))
    )
    result = await session.execute(stmt)
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Thread '{thread_id}' not found")
    _ensure_thread_access(thread, current_user)

    if req.shared_scope:
        current_user.check_scope(req.shared_scope)

    # Auto-generate title from first question if it was "New Investigation"
    if thread.title == "New Investigation" and len(thread.messages) == 0:
        thread.title = req.content[:45] + ("..." if len(req.content) > 45 else "")

    # Mid-thread sharing changes are allowed for owners and admins only.
    if req.shared_scope and req.shared_scope != thread.shared_scope:
        if thread.owner_user_id != current_user.user_id and not current_user.is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the thread owner may change sharing")
        thread.shared_scope = req.shared_scope

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
        shared_scope=thread.shared_scope,
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
    scope = _thread_acl_scope(thread)

    # If client requests SSE stream
    wants_sse = (
        "text/event-stream" in request.headers.get("accept", "")
        or request.query_params.get("stream") == "true"
    )

    if wants_sse:
        started = time.perf_counter()
        token_queue: asyncio.Queue[str | None] = asyncio.Queue()
        first_token_at: float | None = None
        ttft_ms: float | None = None

        def token_sink(token: str) -> None:
            nonlocal first_token_at, ttft_ms
            if not token:
                return
            if first_token_at is None:
                first_token_at = time.perf_counter()
                ttft_ms = round((first_token_at - started) * 1000.0, 2)
            token_queue.put_nowait(token)

        async def event_generator():
            yield _sse(
                "stage",
                {"id": "condense", "label": "Condensing query", "status": "in_progress"},
            )
            await asyncio.sleep(0.02)

            async def run_and_signal() -> dict[str, Any]:
                try:
                    return await run_with_ask_budget(
                        orchestrator.run(
                            query=req.content,
                            acl_scope=scope,
                            thread_id=thread_id,
                            thread_history=history,
                            owner_user_id=current_user.user_id,
                            is_admin=current_user.is_admin,
                            answer_policy=req.answer_policy,
                            token_sink=token_sink,
                        )
                    )
                finally:
                    token_queue.put_nowait(None)

            task = asyncio.create_task(run_and_signal())
            try:
                while True:
                    token = await token_queue.get()
                    if token is None:
                        break
                    yield _sse("token", {"token": token})
                state = await task
            except AskBudgetExceededError as exc:
                yield _sse("error", {"detail": str(exc)})
                return
            except Exception as exc:
                logger.exception("Thread stream failed")
                yield _sse("error", {"detail": str(exc)})
                return
            finally:
                if not task.done():
                    task.cancel()

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
            source_kind = state.get("source_kind", "docs")
            web_sources = list(state.get("web_sources", []) or [])
            query_id = state.get("query_id")
            answer_id = state.get("answer_id")
            metadata = build_answer_metadata(state)

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
            yield f"event: stage\ndata: {json.dumps(stages[4])}\n\n"
            yield f"event: citations\ndata: {json.dumps(citations)}\n\n"

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
                    source_kind=source_kind,
                    answer_metadata=metadata,
                    web_sources=web_sources,
                    query_id=query_id,
                    answer_id=answer_id,
                    created_at=datetime.now(UTC),
                )
                persist_session.add(asst_record)
                await _stage_chat_graph(
                    session=persist_session,
                    text=answer,
                    thread_id=thread_id,
                    shared_scope=thread.shared_scope,
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
                "source_kind": source_kind,
                "source": metadata["source"],
                "answer_path": metadata["answer_path"],
                "top_score": metadata["top_score"],
                "stage_timings_ms": metadata["stage_timings_ms"],
                "web_sources": web_sources,
                "query_id": query_id,
                "answer_id": answer_id,
                "ttft_ms": ttft_ms,
                "created_at": datetime.now(UTC).isoformat(),
            }
            yield _sse("done", final_msg)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # Non-streaming POST execution
    try:
        state = await run_with_ask_budget(
            orchestrator.run(
                query=req.content,
                acl_scope=scope,
                thread_id=thread_id,
                thread_history=history,
                owner_user_id=current_user.user_id,
                is_admin=current_user.is_admin,
                answer_policy=req.answer_policy,
            )
        )
    except AskBudgetExceededError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc

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
    source_kind = state.get("source_kind", "docs")
    web_sources = list(state.get("web_sources", []) or [])
    query_id = state.get("query_id")
    answer_id = state.get("answer_id")
    metadata = build_answer_metadata(state)

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
        source_kind=source_kind,
        answer_metadata=metadata,
        web_sources=web_sources,
        query_id=query_id,
        answer_id=answer_id,
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
        shared_scope=thread.shared_scope,
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

    # Append only to a user-supplied candidate eval directory. There is no
    # bundled candidate dataset to mutate.
    configured_dir = get_settings().EVAL_CANDIDATES_DIR
    if not configured_dir:
        raise HTTPException(
            status_code=400,
            detail="EVAL_CANDIDATES_DIR must be configured to export candidates.",
        )
    evals_dir = Path(configured_dir).expanduser().resolve()
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
        .where(ThreadRecord.thread_id == thread_id)
        .options(selectinload(ThreadRecord.messages))
    )
    result = await session.execute(stmt)
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Thread '{thread_id}' not found")
    _ensure_thread_access(thread, current_user)

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
        "source_kind": asst_msg.source_kind,
        "source": (getattr(asst_msg, "answer_metadata", None) or {}).get("source", "docs"),
        "answer_path": list(
            (getattr(asst_msg, "answer_metadata", None) or {}).get("answer_path") or []
        ),
        "top_score": float(
            (getattr(asst_msg, "answer_metadata", None) or {}).get("top_score") or 0.0
        ),
        "stage_timings_ms": dict(
            (getattr(asst_msg, "answer_metadata", None) or {}).get("stage_timings_ms") or {}
        ),
        "web_sources": list(asst_msg.web_sources or []),
        "query_id": asst_msg.query_id,
        "answer_id": asst_msg.answer_id,
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
    scope = _thread_acl_scope(thread)

    try:
        state = await run_with_ask_budget(
            orchestrator.run(
                query=user_query,
                acl_scope=scope,
                thread_id=thread_id,
                thread_history=history,
                owner_user_id=current_user.user_id,
                is_admin=current_user.is_admin,
                answer_policy="grounded_plus_web",
            )
        )
    except AskBudgetExceededError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc

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
    source_kind = state.get("source_kind", "docs")
    web_sources = list(state.get("web_sources", []) or [])
    query_id = state.get("query_id")
    answer_id = state.get("answer_id")
    metadata = build_answer_metadata(state)

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
    asst_msg.source_kind = source_kind
    asst_msg.answer_metadata = metadata
    asst_msg.web_sources = web_sources
    asst_msg.query_id = query_id
    asst_msg.answer_id = answer_id

    await session.flush()
    await session.refresh(asst_msg)
    return _to_message_item(asst_msg)
