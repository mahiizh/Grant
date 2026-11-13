import logging

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.schemas.cache import (
    CacheInvalidationRecord,
    CacheInvalidationsResponse,
    CacheStatsResponse,
)
from app.db.models import OutboxEventRecord
from app.db.postgres import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cache", tags=["cache"])


@router.get("/stats", response_model=CacheStatsResponse)
async def get_cache_stats(
    window: str = Query("24h"),
) -> CacheStatsResponse:
    """Retrieve telemetry time series for exact and semantic cache performance.

    Cache hits/misses are counted in process memory only and are never exported,
    so a cross-process time series cannot be reconstructed. Returning 501 is
    preferable to inventing a hit rate.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Cache telemetry is not implemented: hit/miss counters are not persisted "
            "or exported, so no per-window time series exists."
        ),
    )


@router.get("/invalidations", response_model=CacheInvalidationsResponse)
async def get_cache_invalidations() -> CacheInvalidationsResponse:
    """Audit log of semantic cache invalidations triggered by mutations in outbox."""
    async with get_session() as session:
        stmt = (
            select(OutboxEventRecord)
            .where(OutboxEventRecord.event_type == "CACHE_INVALIDATED")
            .order_by(OutboxEventRecord.created_at.desc())
            .limit(50)
        )
        res = await session.execute(stmt)
        events = list(res.scalars().all())

    records: list[CacheInvalidationRecord] = []
    for ev in events:
        payload = ev.payload or {}
        records.append(
            CacheInvalidationRecord(
                id=ev.event_id,
                timestamp=ev.created_at.isoformat(),
                trigger_event=ev.event_type,
                affected_keys_count=1,
                reason=payload.get("reason", "document_mutation"),
                acl_scope="data-platform",
            )
        )

    return CacheInvalidationsResponse(invalidations=records, total=len(records))
