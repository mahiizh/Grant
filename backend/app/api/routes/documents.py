import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.api.schemas.documents import (
    DocumentDeleteResponse,
    DocumentImpactResponse,
    DocumentRecord,
    DocumentsResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
    StoreDeleteResult,
)
from app.cache.invalidation import CacheInvalidator
from app.core.auth import AuthenticatedUser, get_current_user
from app.db.models import DocumentRecord as DBDocumentRecord
from app.db.models import IngestionJobRecord, OutboxEventRecord
from app.db.postgres import DocumentRepository, get_session
from app.indexing.deletion import verify_document_deleted
from app.indexing.neo4j_indexer import Neo4jIndexer
from app.indexing.outbox_worker import OutboxWorker
from app.indexing.qdrant_indexer import EntityVectorIndex, QdrantIndexer
from app.ingestion.parse import parse_markdown

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=DocumentsResponse)
async def list_documents(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DocumentsResponse:
    """List ingested documents owned by the current user."""
    async with get_session() as session:
        stmt = (
            select(DBDocumentRecord)
            .options(selectinload(DBDocumentRecord.chunks))
            .where(DBDocumentRecord.owner_user_id == current_user.user_id)
        )
        result = await session.execute(stmt)
        docs = list(result.scalars().all())

    doc_list: list[DocumentRecord] = []
    for d in docs:
        meta = d.metadata_json or {}
        doc_list.append(
            DocumentRecord(
                id=d.doc_id,
                title=d.title,
                file_type="markdown" if d.source_uri.endswith(".md") else "text",
                size_kb=max(1, len(d.content.encode("utf-8")) // 1024),
                chunks=len(d.chunks),
                entities_extracted=meta.get("entity_count", 0),
                relations_extracted=meta.get("relation_count", 0),
                tier=d.source_tier,
                ingested_at=d.ingested_at.isoformat() if d.ingested_at else "",
                target_node_id=d.doc_id,
                tokens=meta.get("tokens", 0),
                cost_usd=float(meta.get("cost_usd", 0.0)),
                extraction_engine=str(meta.get("extraction_engine", "unknown")),
                extraction_model=str(meta.get("extraction_model", "")),
                extraction_status=str(meta.get("extraction_status", "unknown")),
            )
        )

    return DocumentsResponse(documents=doc_list, total=len(doc_list))


@router.post("", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DocumentUploadResponse:
    """Persist the upload and enqueue a job; the worker does all heavy work."""
    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()
    if filename.endswith(".pdf") or content_type == "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="PDF upload is not supported. Please upload Markdown (.md) or CSV (.csv) documents.",
        )

    content_bytes = await file.read()
    content_str = content_bytes.decode("utf-8", errors="replace")
    source_uri = file.filename or "uploaded.md"
    parsed = parse_markdown(content_str, source_path=source_uri)
    job_id = f"job-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC)

    # Only a row write and a commit happen on the request path. Parsing, GLiNER,
    # entity resolution, and Qdrant/Neo4j indexing move to the worker process.
    async with get_session() as session:
        session.add(
            IngestionJobRecord(
                job_id=job_id,
                document_id=parsed.doc_id,
                owner_user_id=current_user.user_id,
                file_name=source_uri,
                content=content_bytes,
                status="queued",
                active_step="queued",
                step_index=0,
                extraction_status="pending",
                created_at=now,
            )
        )

    return DocumentUploadResponse(
        document_id=parsed.doc_id,
        job_id=job_id,
        title=parsed.title,
        status="queued",
        message="Upload accepted; background worker will parse, extract, and index it.",
    )


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DocumentStatusResponse:
    """Get current ingestion job progress for a document or job id."""
    async with get_session() as session:
        job_stmt = select(IngestionJobRecord).where(
            or_(
                IngestionJobRecord.document_id == document_id,
                IngestionJobRecord.job_id == document_id,
            )
        )
        if current_user.user_id is not None:
            job_stmt = job_stmt.where(
                IngestionJobRecord.owner_user_id == current_user.user_id
            )
        job = (
            await session.execute(
                job_stmt.order_by(IngestionJobRecord.created_at.desc()).limit(1)
            )
        ).scalar_one_or_none()

        if job is not None:
            ingest_ms = None
            if job.completed_at is not None and job.created_at is not None:
                ingest_ms = round(
                    (job.completed_at - job.created_at).total_seconds() * 1000.0, 2
                )
            return DocumentStatusResponse(
                id=job.document_id,
                job_id=job.job_id,
                status=job.status,
                active_step=job.active_step,
                step_index=job.step_index,
                total_steps=6,
                entities=job.entity_count,
                relations=job.relation_count,
                extraction_engine=job.extraction_engine,
                extraction_model=job.extraction_model,
                extraction_status=job.extraction_status,
                error=job.error,
                ingest_ms=ingest_ms,
            )

        stmt = (
            select(DBDocumentRecord)
            .options(selectinload(DBDocumentRecord.chunks))
            .where(
                DBDocumentRecord.doc_id == document_id,
                DBDocumentRecord.owner_user_id == current_user.user_id,
            )
        )
        res = await session.execute(stmt)
        doc = res.scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        meta = doc.metadata_json or {}
        outbox_stmt = select(OutboxEventRecord).where(
            OutboxEventRecord.payload["doc_id"].astext == document_id,
            OutboxEventRecord.status == "PENDING",
        )
        outbox_res = await session.execute(outbox_stmt)
        pending_events = len(outbox_res.scalars().all())

    is_processing = pending_events > 0
    return DocumentStatusResponse(
        id=doc.doc_id,
        status="processing" if is_processing else "completed",
        active_step="outbox_sync" if is_processing else "complete",
        step_index=3 if is_processing else 6,
        total_steps=6,
        entities=meta.get("entity_count", 0),
        relations=meta.get("relation_count", 0),
        extraction_engine=str(meta.get("extraction_engine", "unknown")),
        extraction_model=str(meta.get("extraction_model", "")),
        extraction_status=str(meta.get("extraction_status", "unknown")),
    )


@router.get("/{document_id}/impact", response_model=DocumentImpactResponse)
async def get_document_impact(
    document_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DocumentImpactResponse:
    """Calculate blast radius before deleting a document."""
    async with get_session() as session:
        stmt = (
            select(DBDocumentRecord)
            .options(selectinload(DBDocumentRecord.chunks))
            .where(
                DBDocumentRecord.doc_id == document_id,
                DBDocumentRecord.owner_user_id == current_user.user_id,
            )
        )
        res = await session.execute(stmt)
        doc = res.scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        chunk_ids = [c.chunk_id for c in doc.chunks]

    # Calculate blast radius score
    score = round(min(1.0, (len(chunk_ids) * 0.1) + 0.2), 2)
    return DocumentImpactResponse(
        document_id=document_id,
        affected_entities=[f"Entity_{cid}" for cid in chunk_ids[:5]],
        affected_relations=[f"Rel_{cid}" for cid in chunk_ids[:3]],
        affected_chunks=chunk_ids,
        blast_radius_score=score,
    )


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DocumentDeleteResponse:
    """Cascade delete a document and verify that every store is actually clean."""
    async with get_session() as session:
        stmt = (
            select(DBDocumentRecord)
            .options(selectinload(DBDocumentRecord.chunks))
            .where(
                DBDocumentRecord.doc_id == document_id,
                DBDocumentRecord.owner_user_id == current_user.user_id,
            )
        )
        doc = (await session.execute(stmt)).scalar_one_or_none()
        if doc is None:
            raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")
        # Snapshot the chunk IDs before the row disappears; verification checks
        # that none of these still exist downstream.
        chunk_ids = [chunk.chunk_id for chunk in doc.chunks]
        await DocumentRepository.delete_document(session=session, doc_id=document_id)

    qdrant = QdrantIndexer()
    neo4j = Neo4jIndexer()
    invalidator = CacheInvalidator()
    entity_index = EntityVectorIndex()
    try:
        # Process outbox events (delete from Qdrant and Neo4j, purge caches).
        worker = OutboxWorker(
            qdrant_indexer=qdrant,
            neo4j_indexer=neo4j,
            cache_invalidator=invalidator,
            entity_indexer=entity_index,
        )
        await worker.drain()

        async with get_session() as session:
            results = await verify_document_deleted(
                session=session,
                doc_id=document_id,
                chunk_ids=chunk_ids,
                qdrant=qdrant,
                neo4j=neo4j,
                invalidator=invalidator,
            )
    finally:
        await qdrant.close()
        await neo4j.close()
        await entity_index.close()

    stores = [
        StoreDeleteResult(
            store=result.store,
            remaining=result.remaining,
            cleared=result.cleared,
            error=result.error,
        )
        for result in results
    ]
    cleared = [result.store for result in results if result.cleared]
    verified = all(result.cleared for result in results)
    return DocumentDeleteResponse(
        document_id=document_id,
        success=verified,
        verified=verified,
        stores=stores,
        stores_cleared=cleared,
    )
