"""Bi-temporal conflict detection and supersession management for ingested documents."""

import logging
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import DocumentRecord
from app.db.outbox import OutboxEventType, OutboxService
from app.domain import Chunk, Document

logger = logging.getLogger(__name__)

# Matches doc_id ending in version suffix, e.g. "doc_sla_payments_v2" -> ("doc_sla_payments", 2)
VERSION_SUFFIX_PATTERN = re.compile(r"^(.*?)(?:_v(\d+))?$", re.IGNORECASE)


def extract_document_root_and_version(doc_id: str) -> tuple[str, int]:
    """Extract base document ID and version integer.

    Examples:
        "doc_sla_payments_v2" -> ("doc_sla_payments", 2)
        "doc_sla_payments_v1" -> ("doc_sla_payments", 1)
        "doc_rfc_001" -> ("doc_rfc_001", 1)
    """
    match = VERSION_SUFFIX_PATTERN.match(doc_id)
    if not match:
        return doc_id, 1
    root = match.group(1) or doc_id
    version_str = match.group(2)
    version = int(version_str) if version_str else 1
    return root, version


async def close_superseded_document_versions(
    session: AsyncSession,
    new_doc: Document,
) -> list[str]:
    """Find prior active document versions and terminate their valid_to timestamp.

    When a newer version of a document is ingested (e.g. doc_sla_payments_v2 with
    valid_from=2026-03-15), any prior version (e.g. doc_sla_payments_v1) whose
    valid_to is either unclosed (None) or extends past the new document's valid_from
    must have its validity terminated at new_valid_from.

    Stages CHUNK_UPSERTED outbox events so downstream stores (Qdrant & Neo4j) update
    their temporal payloads accordingly.

    Returns:
        List of superseded doc_ids that were closed.
    """
    root, new_version = extract_document_root_and_version(new_doc.doc_id)
    if new_version <= 1:
        return []

    new_valid_from = new_doc.temporal.valid_from
    if new_valid_from.tzinfo is None:
        new_valid_from = new_valid_from.replace(tzinfo=UTC)

    stmt = (
        select(DocumentRecord)
        .options(selectinload(DocumentRecord.chunks))
        .where(
            DocumentRecord.doc_id.startswith(root),
            DocumentRecord.doc_id != new_doc.doc_id,
        )
    )
    result = await session.execute(stmt)
    candidates = result.scalars().all()

    closed_doc_ids: list[str] = []

    for old_doc in candidates:
        old_root, old_version = extract_document_root_and_version(old_doc.doc_id)
        if old_root != root or old_version >= new_version:
            continue

        old_valid_to = old_doc.valid_to
        if old_valid_to is not None and old_valid_to.tzinfo is None:
            old_valid_to = old_valid_to.replace(tzinfo=UTC)

        if old_valid_to is None or old_valid_to > new_valid_from:
            logger.info(
                "Closing superseded document %s validity to %s (superseded by %s)",
                old_doc.doc_id,
                new_valid_from.isoformat(),
                new_doc.doc_id,
            )
            old_doc.valid_to = new_valid_from
            closed_doc_ids.append(old_doc.doc_id)

            for chunk_rec in old_doc.chunks:
                chunk_rec.valid_to = new_valid_from
                payload: dict[str, Any] = {
                    "chunk_id": chunk_rec.chunk_id,
                    "doc_id": chunk_rec.doc_id,
                    "index": chunk_rec.chunk_index,
                    "text": chunk_rec.text,
                    "tokens": chunk_rec.tokens,
                    "acl_scope": {
                        "tenant_id": chunk_rec.acl_tenant_id,
                        "allowed_roles": chunk_rec.acl_allowed_roles or [],
                        "allowed_groups": chunk_rec.acl_allowed_groups or [],
                        "is_public": chunk_rec.acl_is_public,
                    },
                    "temporal": {
                        "valid_from": chunk_rec.valid_from.isoformat()
                        if chunk_rec.valid_from
                        else None,
                        "valid_to": new_valid_from.isoformat(),
                    },
                    "source_tier": chunk_rec.source_tier,
                }
                OutboxService.stage_event(
                    session=session,
                    event_type=OutboxEventType.CHUNK_UPSERTED,
                    aggregate_type="chunk",
                    aggregate_id=chunk_rec.chunk_id,
                    payload=payload,
                )

    return closed_doc_ids


def close_superseded_chunks_in_memory(
    chunks: list[Chunk],
    new_doc_id: str,
    new_valid_from: datetime,
) -> list[str]:
    """In-memory helper for hermetic test environments and mock retrievers."""
    root, new_version = extract_document_root_and_version(new_doc_id)
    if new_version <= 1:
        return []

    target_time = (
        new_valid_from if new_valid_from.tzinfo is not None else new_valid_from.replace(tzinfo=UTC)
    )
    closed: list[str] = []

    for i, c in enumerate(chunks):
        c_root, c_version = extract_document_root_and_version(c.doc_id)
        if c_root == root and c_version < new_version:
            curr_valid_to = c.temporal.valid_to
            if curr_valid_to is not None and curr_valid_to.tzinfo is None:
                curr_valid_to = curr_valid_to.replace(tzinfo=UTC)

            if curr_valid_to is None or curr_valid_to > target_time:
                chunks[i] = c.model_copy(update={"temporal": c.temporal.invalidate(target_time)})
                if c.doc_id not in closed:
                    closed.append(c.doc_id)

    return closed
