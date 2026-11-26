"""Standalone background worker for uploaded documents.

Only this process imports and runs the ingestion pipeline, so GLiNER is loaded
here and never in the API process. Jobs are claimed from PostgreSQL; the raw
upload bytes live on the job row itself.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import IngestionJobRecord
from app.db.postgres import get_session
from app.indexing.outbox_worker import OutboxWorker
from app.ingestion.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)

# Stage labels mirrored by the UI stepper.
_STEP_PARSE = 1
_STEP_CHUNK = 2
_STEP_EXTRACT = 3
_STEP_RESOLVE = 4
_STEP_INDEX_QDRANT = 5
_STEP_INDEX_NEO4J = 6


async def claim_next_job() -> IngestionJobRecord | None:
    """Atomically claim one queued job for this worker."""
    async with get_session() as session:
        stmt = (
            select(IngestionJobRecord)
            .where(IngestionJobRecord.status == "queued")
            .order_by(IngestionJobRecord.created_at)
            .limit(1)
        )
        job = (await session.execute(stmt)).scalar_one_or_none()
        if job is None:
            return None
        job.status = "processing"
        job.active_step = "parse"
        job.step_index = _STEP_PARSE
        job.started_at = datetime.now(UTC)
        job.extraction_status = "running"
        await session.flush()
        snapshot = job
    return snapshot


async def _update_job(job_id: str, **fields: Any) -> None:
    async with get_session() as session:
        job = await session.get(IngestionJobRecord, job_id)
        if job is None:
            return
        for key, value in fields.items():
            setattr(job, key, value)


async def process_job(job: IngestionJobRecord) -> bool:
    """Parse, extract, resolve, index, and mark one job complete."""
    logger.info("Processing ingestion job %s for %s", job.job_id, job.document_id)
    try:
        await _update_job(
            job.job_id,
            active_step="chunk",
            step_index=_STEP_CHUNK,
        )
        content = bytes(job.content).decode("utf-8", errors="replace")
        await _update_job(
            job.job_id,
            active_step="extract",
            step_index=_STEP_EXTRACT,
        )

        # GLiNER and entity resolution are loaded here, off the API request path.
        async with get_session() as session:
            summary = await IngestionPipeline.ingest_text(
                session=session,
                content=content,
                source_uri=job.file_name,
                owner_user_id=job.owner_user_id,
            )
            doc_id = summary.doc_id
            entity_count = summary.entity_count
            relation_count = summary.relation_count

        await _update_job(
            job.job_id,
            document_id=doc_id,
            active_step="resolve",
            step_index=_STEP_RESOLVE,
            entity_count=entity_count,
            relation_count=relation_count,
            extraction_engine="gliner",
            extraction_status="completed",
        )

        await _update_job(
            job.job_id,
            active_step="index_qdrant",
            step_index=_STEP_INDEX_QDRANT,
        )
        await OutboxWorker().drain()
        await _update_job(
            job.job_id,
            active_step="index_neo4j",
            step_index=_STEP_INDEX_NEO4J,
        )

        await _update_job(
            job.job_id,
            status="completed",
            active_step="complete",
            step_index=_STEP_INDEX_NEO4J,
            extraction_status="completed",
            completed_at=datetime.now(UTC),
            error=None,
        )
        logger.info("Completed ingestion job %s -> %s", job.job_id, doc_id)
        return True
    except Exception as exc:
        logger.exception("Ingestion job %s failed", job.job_id)
        await _update_job(
            job.job_id,
            status="failed",
            active_step="failed",
            extraction_status="failed",
            error=str(exc)[:1000],
            completed_at=datetime.now(UTC),
        )
        return False


async def run_worker_loop(poll_interval: float = 0.25) -> None:
    """Poll for queued jobs forever, processing one at a time."""
    logger.info("Starting document ingestion worker...")
    settings = get_settings()
    logger.info("Worker stores: db=%s qdrant=%s neo4j=%s", settings.POSTGRES_DB, settings.QDRANT_COLLECTION, settings.NEO4J_URI)
    while True:
        try:
            job = await claim_next_job()
            if job is None:
                await asyncio.sleep(poll_interval)
                continue
            await process_job(job)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Ingestion worker loop error: %s", exc)
            await asyncio.sleep(1.0)


if __name__ == "__main__":  # pragma: no cover - entry point
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker_loop())
