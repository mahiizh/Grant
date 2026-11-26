"""Step 5: every answer path persists source, path, top score and timings."""

from typing import Any, cast

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.acl import ACLScope
from app.db.models import AnswerRecord, Base
from app.history.service import QueryHistoryService
from app.orchestration.workflow import RAGOrchestrator
from app.web_grounding.web import WebPage
from tests.fakes.fake_gateway import FakeModelGateway
from tests.fakes.fake_web import FakeWebClient, FakeWebIngestor
from tests.unit.test_slice2_web_grounding import (
    EmptyGraphRetriever,
    EmptyHybridRetriever,
    EvidenceHybridRetriever,
    FakeHistory,
    NotFoundGateway,
    build_orchestrator,
)

METADATA_FIELDS = ("source", "answer_path", "top_score", "stage_timings_ms")

WEB_PAGE = WebPage(
    url="https://example.com/metadata",
    title="Metadata source",
    text="The incident timeline describes detection and containment steps.",
    fetched_at="2026-11-26T00:00:00Z",
)


def _build(
    *,
    history: FakeHistory,
    hybrid: Any,
    gateway: Any,
    web_client: Any = None,
    web_ingestor: Any = None,
) -> RAGOrchestrator:
    return build_orchestrator(
        history=history,
        hybrid=hybrid,
        gateway=gateway,
        web_client=web_client,
        web_ingestor=web_ingestor,
        record_history=True,
    )


async def _run_path(
    *,
    hybrid: Any,
    gateway: Any,
    answer_policy: str,
    web_client: Any = None,
    web_ingestor: Any = None,
) -> tuple[FakeHistory, dict[str, Any]]:
    history = FakeHistory()
    orchestrator = _build(
        history=history,
        hybrid=hybrid,
        gateway=gateway,
        web_client=web_client,
        web_ingestor=web_ingestor,
    )
    state = await orchestrator.run(
        query="What happened in the incident timeline?",
        answer_policy=cast(Any, answer_policy),
        owner_user_id="usr_alice_01",
    )
    return history, state


def _assert_recorded(call: dict[str, Any], source: str, path: list[str]) -> None:
    for field in METADATA_FIELDS:
        assert field in call, f"missing answer metadata field {field}"
    assert call["source"] == source
    assert call["answer_path"] == path
    assert isinstance(call["top_score"], float)
    assert isinstance(call["stage_timings_ms"], dict)
    assert call["stage_timings_ms"], "stage timings must not be empty"


@pytest.mark.anyio
async def test_docs_path_records_all_answer_metadata() -> None:
    history, state = await _run_path(
        hybrid=EvidenceHybridRetriever(),
        gateway=FakeModelGateway(),
        answer_policy="grounded_only",
    )
    assert len(history.record_calls) == 1
    _assert_recorded(history.record_calls[0], "docs", ["docs"])
    assert history.record_calls[0]["top_score"] == 0.9
    assert state["stage_timings_ms"]


@pytest.mark.anyio
async def test_web_path_records_all_answer_metadata() -> None:
    history, state = await _run_path(
        hybrid=EmptyHybridRetriever(),
        gateway=FakeModelGateway(),
        answer_policy="grounded_plus_web",
        web_client=FakeWebClient(pages=[WEB_PAGE]),
        web_ingestor=FakeWebIngestor(),
    )
    assert len(history.record_calls) == 1
    _assert_recorded(history.record_calls[0], "web", ["docs", "web"])
    assert state["source_kind"] == "web"


@pytest.mark.anyio
async def test_model_path_records_all_answer_metadata() -> None:
    history, state = await _run_path(
        hybrid=EmptyHybridRetriever(),
        gateway=FakeModelGateway(),
        answer_policy="grounded_plus_web",
        web_client=FakeWebClient(),
        web_ingestor=FakeWebIngestor(),
    )
    assert len(history.record_calls) == 1
    _assert_recorded(history.record_calls[0], "model", ["docs", "web", "model"])
    assert state["source_kind"] == "unverified"


@pytest.mark.anyio
async def test_abstain_path_records_all_answer_metadata() -> None:
    history, state = await _run_path(
        hybrid=EvidenceHybridRetriever(),
        gateway=NotFoundGateway(),
        answer_policy="grounded_only",
    )
    assert len(history.record_calls) == 1
    _assert_recorded(history.record_calls[0], "abstain", ["docs", "abstain"])
    assert state["is_abstention"] is True


@pytest.mark.anyio
async def test_answer_record_persists_metadata_fields() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as session:
            _, answer_id = await QueryHistoryService().record(
                session=session,
                raw_query="What changed?",
                rewritten_query="What changed?",
                answer="A grounded answer.",
                evidence=[],
                source_kind="web",
                web_sources=[],
                answer_policy="grounded_plus_web",
                acl_scope=ACLScope.public(),
                owner_user_id=None,
                thread_id=None,
                source="web",
                answer_path=["docs", "web"],
                top_score=0.81234,
                stage_timings_ms={"web": 12.5, "llm": 34.5},
            )
            record = (
                await session.execute(
                    select(AnswerRecord).where(AnswerRecord.answer_id == answer_id)
                )
            ).scalar_one()
            assert record.source == "web"
            assert record.path == ["docs", "web"]
            assert record.top_score == 0.81234
            assert record.stage_timings_ms == {"web": 12.5, "llm": 34.5}
    finally:
        await engine.dispose()
