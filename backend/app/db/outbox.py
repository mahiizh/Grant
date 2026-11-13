import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OutboxEventRecord


class OutboxEventType(StrEnum):
    DOCUMENT_INGESTED = "DOCUMENT_INGESTED"
    DOCUMENT_DELETED = "DOCUMENT_DELETED"
    CHUNK_UPSERTED = "CHUNK_UPSERTED"
    CACHE_INVALIDATED = "CACHE_INVALIDATED"


class OutboxStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


class OutboxService:
    """Manages transactional staging, retrieval, and state transitions for outbox events."""

    @staticmethod
    def stage_event(
        session: AsyncSession,
        event_type: OutboxEventType | str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
        max_retries: int = 3,
    ) -> OutboxEventRecord:
        """Stage an outbox event within the caller's active database transaction."""
        event_id = f"evt_{uuid.uuid4().hex[:16]}"
        type_str = event_type.value if isinstance(event_type, OutboxEventType) else str(event_type)

        event = OutboxEventRecord(
            event_id=event_id,
            event_type=type_str,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            status=OutboxStatus.PENDING.value,
            retry_count=0,
            max_retries=max_retries,
            created_at=datetime.now(UTC),
        )
        session.add(event)
        return event

    @staticmethod
    async def fetch_pending_events(
        session: AsyncSession,
        limit: int = 50,
    ) -> list[OutboxEventRecord]:
        """Fetch pending or retryable failed events ordered by creation time."""
        stmt = (
            select(OutboxEventRecord)
            .where(
                (OutboxEventRecord.status == OutboxStatus.PENDING.value)
                | (
                    (OutboxEventRecord.status == OutboxStatus.FAILED.value)
                    & (OutboxEventRecord.retry_count < OutboxEventRecord.max_retries)
                )
            )
            .order_by(OutboxEventRecord.created_at.asc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def mark_processed(
        session: AsyncSession,
        event_id: str,
    ) -> OutboxEventRecord | None:
        """Mark an outbox event as successfully processed by downstream indexers."""
        stmt = select(OutboxEventRecord).where(OutboxEventRecord.event_id == event_id)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()
        if event is None:
            return None

        event.status = OutboxStatus.PROCESSED.value
        event.processed_at = datetime.now(UTC)
        return event

    @staticmethod
    async def mark_failed(
        session: AsyncSession,
        event_id: str,
        error_message: str,
    ) -> OutboxEventRecord | None:
        """Record an outbox failure. Transitions to DEAD_LETTER if max_retries exceeded."""
        stmt = select(OutboxEventRecord).where(OutboxEventRecord.event_id == event_id)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()
        if event is None:
            return None

        event.retry_count += 1
        event.last_error = error_message

        if event.retry_count >= event.max_retries:
            event.status = OutboxStatus.DEAD_LETTER.value
        else:
            event.status = OutboxStatus.FAILED.value

        return event

    @staticmethod
    async def get_dead_letter_events(
        session: AsyncSession,
        limit: int = 50,
    ) -> list[OutboxEventRecord]:
        """Query dead-letter events for monitoring and alerting (Action item: INC-2026-04)."""
        stmt = (
            select(OutboxEventRecord)
            .where(OutboxEventRecord.status == OutboxStatus.DEAD_LETTER.value)
            .order_by(OutboxEventRecord.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def reconcile(
        session: AsyncSession,
        processed_retention_days: int = 7,
        now: datetime | None = None,
    ) -> dict[str, int]:
        """Keep the outbox bounded and idempotent.

        * Delete ``PROCESSED`` events older than the retention window so the
          table does not grow without bound.
        * Compact duplicate ``PENDING`` events for the same
          ``(event_type, aggregate_type, aggregate_id)`` to the newest one, so a
          retried or repeated ingest does not queue the same index mutation
          twice.
        """
        current = now or datetime.now(UTC)
        cutoff = current - timedelta(days=processed_retention_days)

        processed_stmt = select(OutboxEventRecord).where(
            OutboxEventRecord.status == OutboxStatus.PROCESSED.value,
            OutboxEventRecord.processed_at.is_not(None),
            OutboxEventRecord.processed_at < cutoff,
        )
        processed_events = list((await session.execute(processed_stmt)).scalars().all())
        for event in processed_events:
            await session.delete(event)

        pending_stmt = (
            select(OutboxEventRecord)
            .where(OutboxEventRecord.status == OutboxStatus.PENDING.value)
            .order_by(OutboxEventRecord.created_at.asc())
        )
        pending_events = list((await session.execute(pending_stmt)).scalars().all())

        seen: dict[tuple[str, str, str], OutboxEventRecord] = {}
        duplicates = 0
        for event in pending_events:
            key = (event.event_type, event.aggregate_type, event.aggregate_id)
            if key in seen:
                # Newer event supersedes the older pending duplicate.
                await session.delete(seen[key])
                duplicates += 1
            seen[key] = event

        return {
            "processed_pruned": len(processed_events),
            "pending_compacted": duplicates,
            "pending_remaining": len(seen),
        }
