import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.schemas.query import EvidenceItem, QueryRequest, QueryResponse
from app.core.auth import AuthenticatedUser, get_current_user
from app.observability.tracer import export_spans_to_db
from app.orchestration.answer_metadata import build_answer_metadata
from app.orchestration.budget import AskBudgetExceededError, run_with_ask_budget
from app.orchestration.workflow import RAGOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["query"])

# Default singleton orchestrator instance
_orchestrator: RAGOrchestrator | None = None


def get_orchestrator() -> RAGOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        # The API records query/answer history for tracing and graph sync, but
        # never reuses it to answer. Tests inject a hermetic orchestrator.
        _orchestrator = RAGOrchestrator(record_history=True, defer_cache_history=True)
    return _orchestrator


def set_orchestrator(orchestrator: RAGOrchestrator) -> None:
    """Setter for injecting configured orchestrators in tests."""
    global _orchestrator
    _orchestrator = orchestrator


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def _build_response(request: QueryRequest, state: dict[str, Any]) -> QueryResponse:
    """Build the common QueryResponse payload for JSON and SSE callers."""
    evidence_items = [
        EvidenceItem(
            chunk_id=ev.chunk_id,
            doc_id=ev.doc_id,
            text=ev.text,
            score=ev.score,
            retrieval_method=ev.retrieval_method,
            path=ev.path,
        )
        for ev in state.get("evidence", [])
    ]
    metadata = build_answer_metadata(state)
    return QueryResponse(
        query=request.query,
        answer=state.get("answer", ""),
        strategy_used=state.get("route", "vector"),
        is_cached=state.get("is_cached", False),
        is_abstention=state.get("is_abstention", False),
        evidence=evidence_items,
        path=state.get("path"),
        cost_usd=round(state.get("cost_usd", 0.0), 6),
        latency_ms=round(state.get("latency_ms", 0.0), 2),
        source_kind=state.get("source_kind", "docs"),
        source=str(metadata["source"]),
        answer_path=list(metadata["answer_path"]),
        top_score=float(metadata["top_score"]),
        web_sources=list(state.get("web_sources", []) or []),
        query_id=state.get("query_id"),
        answer_id=state.get("answer_id"),
        stage_timings_ms=dict(state.get("stage_timings_ms", {}) or {}),
    )


async def _export_spans(state: dict[str, Any]) -> None:
    trace_id = state.get("trace_id", "")
    spans = state.get("spans", [])
    if trace_id and spans:
        try:
            await export_spans_to_db(trace_id=trace_id, spans=spans)
        except Exception as e:
            logger.warning("Failed exporting spans to DB: %s", e)


@router.post("", response_model=QueryResponse, status_code=status.HTTP_200_OK)
async def query_pipeline(
    request: QueryRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> QueryResponse:
    """Execute end-to-end GraphRAG pipeline and return grounded answer with citations."""
    orchestrator = get_orchestrator()
    acl_scope = current_user.to_acl_scope(request.scope)

    try:
        state = await run_with_ask_budget(
            orchestrator.run(
                query=request.query,
                acl_scope=acl_scope,
                is_admin=current_user.is_admin,
                thread_id=request.thread_id,
                owner_user_id=current_user.user_id,
                answer_policy=request.answer_policy,
                force_web=request.force_web,
            )
        )
    except AskBudgetExceededError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc

    await _export_spans(state)
    return _build_response(request, state)


@router.post("/stream")
async def query_pipeline_stream(
    request: QueryRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> StreamingResponse:
    """Stream Ask tokens from the live generation call, then emit full metadata."""
    orchestrator = get_orchestrator()
    acl_scope = current_user.to_acl_scope(request.scope)
    started = time.perf_counter()
    first_token_at: float | None = None
    ttft_ms: float | None = None
    token_queue: asyncio.Queue[str | None] = asyncio.Queue()

    def token_sink(token: str) -> None:
        nonlocal first_token_at, ttft_ms
        if not token:
            return
        if first_token_at is None:
            first_token_at = time.perf_counter()
            ttft_ms = round((first_token_at - started) * 1000.0, 2)
        token_queue.put_nowait(token)

    async def event_generator() -> AsyncGenerator[str, None]:
        yield _sse("stage", {"id": "generation", "label": "Generating answer", "status": "running"})

        async def run_and_signal() -> dict[str, Any]:
            try:
                return await run_with_ask_budget(
                    orchestrator.run(
                        query=request.query,
                        acl_scope=acl_scope,
                        is_admin=current_user.is_admin,
                        thread_id=request.thread_id,
                        owner_user_id=current_user.user_id,
                        answer_policy=request.answer_policy,
                        force_web=request.force_web,
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
            logger.exception("Ask stream failed")
            yield _sse("error", {"detail": str(exc)})
            return
        finally:
            if not task.done():
                task.cancel()

        await _export_spans(state)
        response = _build_response(request, state)
        yield _sse("citations", [item.model_dump() for item in response.evidence])
        yield _sse(
            "stage", {"id": "generation", "label": "Generating answer", "status": "completed"}
        )
        yield _sse("done", {**response.model_dump(), "ttft_ms": ttft_ms})

    return StreamingResponse(event_generator(), media_type="text/event-stream")
