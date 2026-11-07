import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OutboxEventRecord
from app.db.outbox import OutboxEventType, OutboxService
from app.db.postgres import get_session
from app.indexing.neo4j_indexer import Neo4jIndexer
from app.indexing.qdrant_indexer import QdrantIndexer

logger = logging.getLogger(__name__)


class OutboxWorker:
    """Asynchronous worker consuming outbox mutation events and syncing downstream stores."""

    def __init__(
        self,
        qdrant_indexer: QdrantIndexer | None = None,
        neo4j_indexer: Neo4jIndexer | None = None,
    ) -> None:
        self.qdrant = qdrant_indexer or QdrantIndexer()
        self.neo4j = neo4j_indexer or Neo4jIndexer()

    async def process_event(
        self,
        session: AsyncSession,
        event: OutboxEventRecord,
    ) -> bool:
        """Route and execute an individual outbox event against Qdrant and Neo4j."""
        payload: dict[str, Any] = event.payload or {}
        event_type = event.event_type

        try:
            if event_type == OutboxEventType.CHUNK_UPSERTED.value:
                chunk_id = payload.get("chunk_id", event.aggregate_id)
                doc_id = payload.get("doc_id", "")
                text = payload.get("text", "")
                acl_scope = payload.get("acl_scope", {})
                temporal = payload.get("temporal", {})

                # 1. Sync to Qdrant (dense + sparse embeddings)
                await self.qdrant.upsert_chunk(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    text=text,
                    payload=payload,
                )

                # 2. Sync Chunk to Neo4j
                await self.neo4j.merge_chunk(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    text=text,
                    acl_scope=acl_scope,
                    temporal=temporal,
                )

                # 3. If extracted entities/relations are bundled with chunk
                for ent in payload.get("entities", []):
                    await self.neo4j.merge_node(
                        entity_id=ent.get("entity_id", ent.get("name")),
                        name=ent.get("name", ""),
                        entity_type=ent.get("entity_type", "Concept"),
                        acl_scope=acl_scope,
                        temporal=temporal,
                        properties={"doc_id": doc_id, "chunk_id": chunk_id},
                    )
                    await self.neo4j.link_chunk_entity(
                        chunk_id=chunk_id,
                        entity_id=ent.get("entity_id", ent.get("name")),
                    )

                for rel in payload.get("relations", []):
                    await self.neo4j.merge_edge(
                        source_id=rel.get("source_entity_id"),
                        target_id=rel.get("target_entity_id"),
                        relation_type=rel.get("relation_type", "RELATED_TO"),
                        acl_scope=acl_scope,
                        temporal=temporal,
                        properties={"doc_id": doc_id},
                    )

            elif event_type == OutboxEventType.DOCUMENT_DELETED.value:
                doc_id = payload.get("doc_id", event.aggregate_id)
                await self.qdrant.delete_by_doc_id(doc_id)
                await self.neo4j.delete_by_doc_id(doc_id)

            elif event_type == OutboxEventType.CACHE_INVALIDATED.value:
                pass

            elif event_type == OutboxEventType.DOCUMENT_INGESTED.value:
                logger.info("Processed DOCUMENT_INGESTED milestone for doc: %s", event.aggregate_id)

            # Mark processed on success
            await OutboxService.mark_processed(session=session, event_id=event.event_id)
            return True

        except Exception as e:
            logger.error("Failed processing outbox event %s: %s", event.event_id, e, exc_info=True)
            await OutboxService.mark_failed(
                session=session,
                event_id=event.event_id,
                error_message=str(e),
            )
            return False

    async def process_batch(
        self,
        session: AsyncSession,
        batch_size: int = 50,
    ) -> int:
        """Fetch and execute pending outbox events in chronological order."""
        events = await OutboxService.fetch_pending_events(session=session, limit=batch_size)
        processed_count = 0

        for event in events:
            success = await self.process_event(session=session, event=event)
            if success:
                processed_count += 1

        return processed_count

    async def drain(self) -> int:
        """Continuously process pending events until the outbox queue is empty."""
        total_processed = 0
        while True:
            async with get_session() as session:
                count = await self.process_batch(session, batch_size=50)
                total_processed += count
                if count == 0:
                    break
        return total_processed


async def run_worker_loop() -> None:
    """Standalone worker loop for running via `make worker`."""
    worker = OutboxWorker()
    logger.info("Starting Outbox Worker daemon...")
    while True:
        try:
            async with get_session() as session:
                processed = await worker.process_batch(session, batch_size=20)
                if processed > 0:
                    logger.info("Outbox worker processed %d events.", processed)
        except Exception as e:
            logger.error("Outbox worker loop error: %s", e)
        await asyncio.sleep(1.0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker_loop())
