from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.schemas.metrics import OverviewMetricsResponse
from app.db.models import ChunkRecord, DocumentRecord, MessageRecord
from app.db.postgres import get_session
from app.indexing.neo4j_indexer import Neo4jIndexer
from app.indexing.qdrant_indexer import QdrantIndexer

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _percentile(values: list[float], fraction: float) -> int | None:
    """Nearest-rank percentile, or ``None`` when no observations exist."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1)))))
    return int(round(ordered[index]))


@router.get("/overview", response_model=OverviewMetricsResponse)
async def get_overview_metrics() -> OverviewMetricsResponse:
    """Aggregated KPIs for the overview dashboard.

    Counts come from PostgreSQL/Qdrant/Neo4j, and latency/cache rates come from
    recorded assistant messages. Metrics the pipeline does not measure (golden-set
    accuracy, wrong-hit rate, cost per correct answer) are returned as ``None``
    rather than fabricated constants.
    """
    async with get_session() as session:
        doc_count_res = await session.execute(select(func.count(DocumentRecord.doc_id)))
        docs_indexed = int(doc_count_res.scalar() or 0)

        chunk_count_res = await session.execute(select(func.count(ChunkRecord.chunk_id)))
        chunks_indexed = int(chunk_count_res.scalar() or 0)

        unverified_res = await session.execute(
            select(func.count(ChunkRecord.chunk_id)).where(
                ChunkRecord.provenance_verified.is_(False)
            )
        )
        unverified_facts = int(unverified_res.scalar() or 0)

        latency_res = await session.execute(
            select(MessageRecord.latency_ms).where(MessageRecord.latency_ms.isnot(None))
        )
        latencies = [float(value) for value in latency_res.scalars().all() if value is not None]

        cache_res = await session.execute(
            select(MessageRecord.cache_status).where(MessageRecord.cache_status.isnot(None))
        )
        cache_statuses = [value for value in cache_res.scalars().all() if value]

    qdrant = QdrantIndexer()
    qdrant_points = await qdrant.count()

    neo4j = Neo4jIndexer()
    entities_indexed = await neo4j.count_nodes()
    relations_indexed = await neo4j.count_edges()
    await neo4j.close()

    cache_hit_rate = (
        round(sum(1 for status in cache_statuses if status == "hit") / len(cache_statuses), 4)
        if cache_statuses
        else None
    )

    return OverviewMetricsResponse(
        docs_indexed=docs_indexed,
        chunks_indexed=chunks_indexed or qdrant_points,
        entities_indexed=entities_indexed,
        relations_indexed=relations_indexed,
        p95_latency_ms=_percentile(latencies, 0.95),
        cache_hit_rate=cache_hit_rate,
        unverified_facts_pending=unverified_facts,
    )
