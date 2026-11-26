import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.query import EvidenceItem, QueryRequest, QueryResponse
from app.core.auth import AuthenticatedUser, get_current_user
from app.observability.tracer import export_spans_to_db
from app.orchestration.budget import AskBudgetExceededError, run_with_ask_budget
from app.orchestration.workflow import RAGOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["query"])

# Default singleton orchestrator instance
_orchestrator: RAGOrchestrator | None = None


def get_orchestrator() -> RAGOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        # The API defaults to grounded_plus_web with history enabled. Tests inject
        # a hermetic orchestrator via set_orchestrator().
        _orchestrator = RAGOrchestrator(history_enabled=True)
    return _orchestrator


def set_orchestrator(orchestrator: RAGOrchestrator) -> None:
    """Setter for injecting configured orchestrators in tests."""
    global _orchestrator
    _orchestrator = orchestrator


@router.post("", response_model=QueryResponse, status_code=status.HTTP_200_OK)
async def query_pipeline(
    request: QueryRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> QueryResponse:
    """Execute end-to-end GraphRAG pipeline and return grounded answer with citations."""
    orchestrator = get_orchestrator()

    # Resolve ACLScope from authenticated identity
    acl_scope = current_user.to_acl_scope(request.scope)

    # Run LangGraph pipeline under the end-to-end Ask budget.
    try:
        state = await run_with_ask_budget(
            orchestrator.run(
                query=request.query,
                acl_scope=acl_scope,
                is_admin=current_user.is_admin,
                thread_id=request.thread_id,
                owner_user_id=current_user.user_id,
                answer_policy=request.answer_policy,
            )
        )
    except AskBudgetExceededError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc

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

    # Export OpenTelemetry spans to PostgreSQL spans table asynchronously
    trace_id = state.get("trace_id", "")
    spans = state.get("spans", [])
    if trace_id and spans:
        try:
            await export_spans_to_db(trace_id=trace_id, spans=spans)
        except Exception as e:
            logger.warning("Failed exporting spans to DB: %s", e)

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
        web_sources=list(state.get("web_sources", []) or []),
        query_id=state.get("query_id"),
        answer_id=state.get("answer_id"),
    )
