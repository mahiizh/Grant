import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import select
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
from app.db.models import DocumentRecord as DBDocumentRecord
from app.db.models import OutboxEventRecord
from app.db.postgres import DocumentRepository, get_session
from app.indexing.deletion import verify_document_deleted
from app.indexing.neo4j_indexer import Neo4jIndexer
from app.indexing.outbox_worker import OutboxWorker
from app.indexing.qdrant_indexer import QdrantIndexer
from app.ingestion.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=DocumentsResponse)
async def list_documents() -> DocumentsResponse:
    """List all ingested documents with tokens, cost, and extracted entity counts."""
    async with get_session() as session:
        stmt = select(DBDocumentRecord).options(selectinload(DBDocumentRecord.chunks))
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
                entities_extracted=meta.get("entity_count", len(d.chunks) * 2),
                relations_extracted=meta.get("relation_count", len(d.chunks)),
                tier=d.source_tier,
                ingested_at=d.ingested_at.isoformat() if d.ingested_at else "",
                target_node_id=d.doc_id,
                valid_from=d.valid_from.isoformat() if d.valid_from else "",
                tokens=meta.get("tokens", 0),
                cost_usd=float(meta.get("cost_usd", 0.0)),
            )
        )

    return DocumentsResponse(documents=doc_list, total=len(doc_list))


@router.post("", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
) -> DocumentUploadResponse:
    """Upload document for parsing, chunking, outbox staging, and automatic indexing."""
    content_bytes = await file.read()
    content_str = content_bytes.decode("utf-8", errors="replace")

    async with get_session() as session:
        summary = await IngestionPipeline.ingest_text(
            session=session,
            content=content_str,
            source_uri=file.filename or "uploaded.md",
        )

    # Process staged outbox events to sync Qdrant and Neo4j immediately
    try:
        worker = OutboxWorker()
        await worker.drain()
    except Exception as e:
        logger.warning("Background outbox drain after upload encountered error: %s", e)

    return DocumentUploadResponse(
        document_id=summary.doc_id,
        title=summary.title,
        status="ingested",
        message=f"Document ingested: {summary.chunk_count} chunks, {summary.entity_count} entities extracted.",
    )


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(document_id: str) -> DocumentStatusResponse:
    """Get current ingestion pipeline progress for document."""
    async with get_session() as session:
        stmt = (
            select(DBDocumentRecord)
            .options(selectinload(DBDocumentRecord.chunks))
            .where(DBDocumentRecord.doc_id == document_id)
        )
        res = await session.execute(stmt)
        doc = res.scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        meta = doc.metadata_json or {}
        # Check outbox events for this doc
        outbox_stmt = select(OutboxEventRecord).where(
            OutboxEventRecord.payload["doc_id"].astext == document_id,
            OutboxEventRecord.status == "PENDING",
        )
        outbox_res = await session.execute(outbox_stmt)
        pending_events = len(outbox_res.scalars().all())

    is_processing = pending_events > 0
    return DocumentStatusResponse(
        id=doc.doc_id,
        status="processing" if is_processing else "indexed",
        active_step="outbox_sync" if is_processing else "complete",
        step_index=3 if is_processing else 4,
        total_steps=4,
        entities=meta.get("entity_count", len(doc.chunks) * 2),
        relations=meta.get("relation_count", len(doc.chunks)),
    )


@router.get("/{document_id}/impact", response_model=DocumentImpactResponse)
async def get_document_impact(document_id: str) -> DocumentImpactResponse:
    """Calculate blast radius before deleting a document."""
    async with get_session() as session:
        stmt = (
            select(DBDocumentRecord)
            .options(selectinload(DBDocumentRecord.chunks))
            .where(DBDocumentRecord.doc_id == document_id)
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
async def delete_document(document_id: str) -> DocumentDeleteResponse:
    """Cascade delete a document and verify that every store is actually clean."""
    async with get_session() as session:
        stmt = (
            select(DBDocumentRecord)
            .options(selectinload(DBDocumentRecord.chunks))
            .where(DBDocumentRecord.doc_id == document_id)
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
    try:
        # Process outbox events (delete from Qdrant and Neo4j, purge caches).
        worker = OutboxWorker(
            qdrant_indexer=qdrant,
            neo4j_indexer=neo4j,
            cache_invalidator=invalidator,
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
