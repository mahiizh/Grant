"""Write fetched web pages back through the normal ingestion pipeline.

Web pages are stored in PostgreSQL as owner-private documents. The outbox then
syncs the resulting chunks and entities to Qdrant and Neo4j exactly as it does
for uploaded documents.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.web_grounding.web import WebPage
from app.core.acl import ACLScope
from app.core.config import get_settings
from app.db.models import ChunkRecord, DocumentRecord
from app.db.postgres import get_session
from app.domain import Evidence, Provenance
from app.domain.ids import generate_doc_id
from app.ingestion.pipeline import IngestionPipeline
from app.retrieval.dense import cosine_similarity
from app.retrieval.embeddings import get_embedding_service
from app.security.injection import INJECTION_PATTERNS

logger = logging.getLogger(__name__)


class WebIngestor(Protocol):
    """Interface used by orchestration; tests supply an in-memory implementation."""

    async def ingest(
        self,
        pages: list[WebPage],
        owner_user_id: str | None,
        acl_scope: ACLScope | None = None,
    ) -> list[Evidence]: ...


@dataclass(frozen=True)
class WebIngestResult:
    doc_id: str
    evidence: list[Evidence]
    ingested: bool


def sanitize_web_markdown(text: str) -> str:
    """Remove known indirect-prompt-injection phrases before persisting a page."""
    sanitized = text
    for pattern in INJECTION_PATTERNS:
        sanitized = pattern.sub("[filtered]", sanitized)
    return sanitized.strip()


def chunk_web_text(
    text: str,
    chunk_chars: int | None = None,
    overlap_chars: int | None = None,
) -> list[str]:
    """Split page text into bounded chunks on word boundaries with overlap."""
    settings = get_settings()
    limit = chunk_chars if chunk_chars is not None else settings.WEB_CHUNK_CHARS
    overlap = overlap_chars if overlap_chars is not None else settings.WEB_CHUNK_OVERLAP_CHARS
    limit = max(1, limit)
    overlap = max(0, min(overlap, limit // 3))

    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        extra = len(word) + (1 if current else 0)
        if current and current_len + extra > limit:
            chunks.append(" ".join(current))
            tail: list[str] = []
            tail_len = 0
            for previous in reversed(current):
                needed = len(previous) + (1 if tail else 0)
                if tail_len + needed > overlap:
                    break
                tail.insert(0, previous)
                tail_len += needed
            current = tail
            current_len = tail_len
            extra = len(word) + (1 if current else 0)
        current.append(word)
        current_len += extra
    if current:
        chunks.append(" ".join(current))
    return chunks


async def _dense_similarity_scores(query: str, texts: Sequence[str]) -> list[float]:
    """Score chunks with the warmed dense model; no new model is loaded per ask."""
    if not texts:
        return []
    service = get_embedding_service()
    query_vector, chunk_vectors = await asyncio.gather(
        service.aembed_query_dense(query),
        service.aembed_chunks_dense(texts),
    )
    return [cosine_similarity(query_vector, vector) for vector in chunk_vectors]


WebScoreFn = Callable[[str, Sequence[str]], Awaitable[Sequence[float]]]


async def select_top_web_chunks(
    query: str,
    evidence: Sequence[Evidence],
    limit: int | None = None,
    scorer: WebScoreFn | None = None,
) -> list[Evidence]:
    """Keep the ``limit`` most question-relevant web chunks, preserving order."""
    cap = limit if limit is not None else get_settings().WEB_TOP_CHUNKS
    if cap <= 0 or len(evidence) <= cap:
        return list(evidence)

    texts = [item.text for item in evidence]
    score_fn = scorer or _dense_similarity_scores
    scores = await score_fn(query, texts)
    if len(scores) != len(evidence):
        raise ValueError("web chunk scorer must return one score per chunk")

    ranked = sorted(
        range(len(evidence)),
        key=lambda idx: (-float(scores[idx]), idx),
    )
    selected: list[Evidence] = []
    for idx in ranked[:cap]:
        selected.append(
            evidence[idx].model_copy(update={"score": round(float(scores[idx]), 4)})
        )
    return selected


def _page_content_hash(page: WebPage, text: str) -> str:
    payload = f"{page.url}\n{page.title}\n{text}".encode()
    return hashlib.sha256(payload).hexdigest()


def _web_doc_id(page: WebPage, owner_user_id: str | None) -> str:
    """Scope the deterministic web document ID to the asking user."""
    return generate_doc_id(f"{owner_user_id or 'public'}:{page.url}", version=1)


def _frontmatter_value(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _build_web_document(
    page: WebPage,
    chunks: Sequence[str],
    doc_id: str,
    content_hash: str,
    fetched_at: str,
) -> str:
    title = page.title.strip() or page.url
    body = "\n\n".join(
        f"## Web chunk {index}\n{chunk}" for index, chunk in enumerate(chunks, start=1)
    )
    return (
        "---\n"
        f"title: {_frontmatter_value(title)}\n"
        f"doc_id: {_frontmatter_value(doc_id)}\n"
        "source_kind: web\n"
        f"url: {_frontmatter_value(page.url)}\n"
        f"fetched_at: {_frontmatter_value(fetched_at)}\n"
        f"web_content_hash: {_frontmatter_value(content_hash)}\n"
        "---\n\n"
        f"# {title}\n\n{body}\n"
    )


class WebPageIngestor:
    """Persist fetched pages through :class:`IngestionPipeline` and drain the outbox."""

    def __init__(self, outbox_worker: Any | None = None, sync_outbox: bool = True) -> None:
        self._outbox_worker = outbox_worker
        self.sync_outbox = sync_outbox

    async def ingest(
        self,
        pages: list[WebPage],
        owner_user_id: str | None,
        acl_scope: ACLScope | None = None,
    ) -> list[Evidence]:
        if not pages:
            return []
        evidence: list[Evidence] = []
        async with get_session() as session:
            for page in pages:
                item = await self._ingest_page(session, page, owner_user_id)
                evidence.extend(item.evidence)
            if self.sync_outbox:
                await self._drain_outbox(session)
        return evidence

    async def _ingest_page(
        self,
        session: AsyncSession,
        page: WebPage,
        owner_user_id: str | None,
    ) -> WebIngestResult:
        text = sanitize_web_markdown(page.text)[: get_settings().WEB_MAX_PAGE_CHARS]
        chunks = chunk_web_text(text)
        if not chunks:
            return WebIngestResult(doc_id="", evidence=[], ingested=False)

        content_hash = _page_content_hash(page, text)
        doc_id = _web_doc_id(page, owner_user_id)
        fetched_at = page.fetched_at.strip() or datetime.now(UTC).isoformat()

        existing = (
            await session.execute(
                select(DocumentRecord).where(DocumentRecord.doc_id == doc_id)
            )
        ).scalar_one_or_none()
        unchanged = (
            existing is not None
            and existing.source_kind == "web"
            and existing.owner_user_id == owner_user_id
            and (existing.metadata_json or {}).get("web_content_hash") == content_hash
        )

        if not unchanged:
            content = _build_web_document(page, chunks, doc_id, content_hash, fetched_at)
            await IngestionPipeline.ingest_text(
                session=session,
                content=content,
                source_uri=page.url,
                acl_scope=ACLScope.owner(owner_user_id) if owner_user_id else ACLScope.public(),
                owner_user_id=owner_user_id,
                # The API process never loads GLiNER; only the worker does.
                use_gliner=False,
            )
        else:
            logger.debug("Skipping unchanged web page for %s", page.url)

        chunk_stmt = (
            select(ChunkRecord)
            .where(ChunkRecord.doc_id == doc_id)
            .order_by(ChunkRecord.chunk_index)
        )
        if owner_user_id is not None:
            chunk_stmt = chunk_stmt.where(ChunkRecord.owner_user_id == owner_user_id)
        chunks = (await session.execute(chunk_stmt)).scalars().all()
        evidence = [
            Evidence(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                text=chunk.text,
                score=1.0,
                retrieval_method="web",
                provenance=Provenance.from_agent(page.url, confidence=0.8),
            )
            for chunk in chunks
        ]
        if not evidence:
            evidence = [
                Evidence(
                    chunk_id=f"web_{content_hash[:12]}",
                    doc_id=doc_id,
                    text=text[:4000],
                    score=1.0,
                    retrieval_method="web",
                    provenance=Provenance.from_agent(page.url, confidence=0.8),
                )
            ]
        return WebIngestResult(
            doc_id=doc_id,
            evidence=evidence,
            ingested=not unchanged,
        )

    async def _drain_outbox(self, session: AsyncSession) -> None:
        worker = self._outbox_worker
        if worker is None:
            from app.indexing.outbox_worker import OutboxWorker

            worker = OutboxWorker()
        await worker.process_batch(session=session, batch_size=50)


_web_ingestor: WebIngestor | None = None


def get_web_ingestor() -> WebIngestor:
    global _web_ingestor
    if _web_ingestor is None:
        _web_ingestor = WebPageIngestor()
    return _web_ingestor


def set_web_ingestor(ingestor: WebIngestor | None) -> None:
    """Replace the process-wide web ingestor (used by tests and local tooling)."""
    global _web_ingestor
    _web_ingestor = ingestor
