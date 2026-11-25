"""Postgres-backed query/answer history used for repeat-answer lookup and graph sync."""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.acl import ACLScope
from app.db.models import AnswerRecord, QueryRecord
from app.db.outbox import OutboxEventType, OutboxService
from app.db.postgres import get_session
from app.domain import Evidence, Provenance
from app.ingestion.extraction import EntityRelationExtractor
from app.ingestion.gliner_extraction import get_gliner_extractor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HistoryHit:
    query_id: str
    answer_id: str
    answer: str
    evidence: list[Evidence]
    source_kind: str
    web_sources: list[dict[str, Any]]


class QueryHistory(Protocol):
    async def lookup(
        self,
        query: str,
        owner_user_id: str | None,
        answer_policy: str = "grounded_plus_web",
        thread_id: str | None = None,
    ) -> HistoryHit | None: ...

    async def record(
        self,
        *,
        session: AsyncSession | None,
        raw_query: str,
        rewritten_query: str,
        answer: str,
        evidence: list[Evidence],
        source_kind: str,
        web_sources: list[dict[str, Any]],
        answer_policy: str,
        acl_scope: ACLScope,
        owner_user_id: str | None,
        thread_id: str | None,
        is_abstention: bool = False,
    ) -> tuple[str, str]: ...


def normalize_query(query: str) -> str:
    return " ".join(query.strip().lower().split())


def query_hash(query: str) -> str:
    return hashlib.sha256(normalize_query(query).encode("utf-8")).hexdigest()


def _evidence_to_dict(ev: Evidence) -> dict[str, Any]:
    return {
        "chunk_id": ev.chunk_id,
        "doc_id": ev.doc_id,
        "text": ev.text,
        "score": ev.score,
        "retrieval_method": ev.retrieval_method,
        "path": ev.path,
        "source_uri": ev.provenance.source_uri,
    }


def _dict_to_evidence(row: dict[str, Any]) -> Evidence:
    return Evidence(
        chunk_id=str(row.get("chunk_id", "")),
        doc_id=str(row.get("doc_id", "")),
        text=str(row.get("text", "")),
        score=float(row.get("score", 0.0)),
        retrieval_method=str(row.get("retrieval_method", "hybrid")),  # type: ignore[arg-type]
        provenance=Provenance.from_document(str(row.get("source_uri", row.get("doc_id", "")))),
        path=row.get("path"),
    )


def _extract_entities(text: str) -> list[Any]:
    try:
        return list(get_gliner_extractor().extract_from_text(text).entities)
    except Exception:
        logger.debug("History entity extraction fell back to heuristics", exc_info=True)
        return list(EntityRelationExtractor.extract_from_text(text).entities)


class QueryHistoryService:
    """Store and retrieve answers, staging Neo4j sync through the transactional outbox."""

    async def lookup(
        self,
        query: str,
        owner_user_id: str | None,
        answer_policy: str = "grounded_plus_web",
        thread_id: str | None = None,
    ) -> HistoryHit | None:
        async with get_session() as session:
            stmt = (
                select(QueryRecord, AnswerRecord)
                .join(AnswerRecord, AnswerRecord.query_id == QueryRecord.query_id)
                .where(QueryRecord.query_hash == query_hash(query))
                .where(QueryRecord.answer_policy == answer_policy)
                .order_by(AnswerRecord.created_at.desc())
                .limit(1)
            )
            if owner_user_id is not None:
                stmt = stmt.where(QueryRecord.owner_user_id == owner_user_id)
            if thread_id is not None:
                stmt = stmt.where(QueryRecord.thread_id == thread_id)
            rows = (await session.execute(stmt)).all()
            if not rows:
                return None
            q, a = rows[0]
            return HistoryHit(
                query_id=q.query_id,
                answer_id=a.answer_id,
                answer=a.content,
                evidence=[_dict_to_evidence(row) for row in (a.citations or [])],
                source_kind=a.source_kind,
                web_sources=list(a.web_sources or []),
            )

    async def record(
        self,
        *,
        session: AsyncSession | None = None,
        raw_query: str,
        rewritten_query: str,
        answer: str,
        evidence: list[Evidence],
        source_kind: str,
        web_sources: list[dict[str, Any]],
        answer_policy: str,
        acl_scope: ACLScope,
        owner_user_id: str | None,
        thread_id: str | None,
        is_abstention: bool = False,
    ) -> tuple[str, str]:
        """Persist query/answer rows and stage their graph nodes and edges."""
        if session is None:
            async with get_session() as owned_session:
                return await self.record(
                    session=owned_session,
                    raw_query=raw_query,
                    rewritten_query=rewritten_query,
                    answer=answer,
                    evidence=evidence,
                    source_kind=source_kind,
                    web_sources=web_sources,
                    answer_policy=answer_policy,
                    acl_scope=acl_scope,
                    owner_user_id=owner_user_id,
                    thread_id=thread_id,
                    is_abstention=is_abstention,
                )

        assert session is not None
        query_id = f"qry-{uuid.uuid4().hex[:12]}"
        answer_id = f"ans-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)

        previous_query_id: str | None = None
        if thread_id:
            prev_stmt = (
                select(QueryRecord.query_id)
                .where(QueryRecord.thread_id == thread_id)
                .order_by(QueryRecord.created_at.desc())
                .limit(1)
            )
            if owner_user_id is not None:
                prev_stmt = prev_stmt.where(QueryRecord.owner_user_id == owner_user_id)
            previous_query_id = (await session.execute(prev_stmt)).scalar_one_or_none()

        session.add(
            QueryRecord(
                query_id=query_id,
                thread_id=thread_id,
                owner_user_id=owner_user_id,
                raw_query=raw_query,
                rewritten_query=rewritten_query or None,
                query_hash=query_hash(rewritten_query or raw_query),
                answer_policy=answer_policy,
                created_at=now,
            )
        )
        session.add(
            AnswerRecord(
                answer_id=answer_id,
                query_id=query_id,
                thread_id=thread_id,
                owner_user_id=owner_user_id,
                content=answer,
                source_kind=source_kind,
                is_abstention=is_abstention,
                citations=[_evidence_to_dict(ev) for ev in evidence],
                web_sources=list(web_sources),
                created_at=now,
            )
        )
        await session.flush()

        query_entities = await self._resolve_entities(
            session=session,
            text=rewritten_query or raw_query,
            source_id=f"chat:query:{query_id}",
            owner_user_id=owner_user_id,
        )
        # Unverified answers must never contribute extracted facts to the graph.
        answer_entities = (
            []
            if source_kind == "unverified" or not answer
            else await self._resolve_entities(
                session=session,
                text=answer,
                source_id=f"chat:answer:{answer_id}",
                owner_user_id=owner_user_id,
            )
        )

        cites = [
            {
                "source_id": ev.chunk_id,
                "source_kind": "web" if ev.retrieval_method == "web" else "document",
                "url": ev.provenance.source_uri
                if ev.retrieval_method == "web"
                else None,
            }
            for ev in evidence
        ]
        OutboxService.stage_event(
            session=session,
            event_type=OutboxEventType.QUERY_ANSWER_UPSERTED,
            aggregate_type="query_answer",
            aggregate_id=query_id,
            payload={
                "query_id": query_id,
                "answer_id": answer_id,
                "previous_query_id": previous_query_id,
                "thread_id": thread_id,
                "owner_user_id": owner_user_id,
                "raw_query": raw_query,
                "rewritten_query": rewritten_query,
                "answer": answer,
                "answer_policy": answer_policy,
                "source_kind": source_kind,
                "is_abstention": is_abstention,
                "acl_scope": acl_scope.model_dump(mode="json"),
                "temporal": {"valid_from": now.isoformat(), "valid_to": None},
                "query_entities": query_entities,
                "answer_entities": answer_entities,
                "cites": cites,
                "web_sources": list(web_sources),
            },
        )
        return query_id, answer_id

    @staticmethod
    async def _resolve_entities(
        *,
        session: AsyncSession,
        text: str,
        source_id: str,
        owner_user_id: str | None,
    ) -> list[dict[str, Any]]:
        entities = _extract_entities(text)
        if not entities:
            return []
        try:
            from app.ingestion.entity_resolution import IngestionEntityResolver

            resolver = IngestionEntityResolver(session=session)
            payload: list[dict[str, Any]] = []
            for entity in entities:
                resolved, _ = await resolver.resolve(
                    name=entity.name,
                    entity_type=entity.entity_type,
                    owner_user_id=owner_user_id,
                    source_id=source_id,
                )
                payload.append(
                    {
                        "entity_id": resolved.entity_id,
                        "name": resolved.name,
                        "entity_type": resolved.entity_type,
                        "aliases": list(resolved.aliases),
                    }
                )
            await resolver.persist_mentions(session)
            return payload
        except Exception:
            logger.exception("History entity resolution failed for %s", source_id)
            return [
                {
                    "entity_id": entity.name,
                    "name": entity.name,
                    "entity_type": entity.entity_type,
                    "aliases": [],
                }
                for entity in entities
            ]


_history: QueryHistory | None = None


def get_query_history() -> QueryHistory:
    global _history
    if _history is None:
        _history = QueryHistoryService()
    return _history


def set_query_history(history: QueryHistory | None) -> None:
    global _history
    _history = history
