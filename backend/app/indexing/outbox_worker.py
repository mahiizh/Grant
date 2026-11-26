import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.invalidation import CacheInvalidator
from app.db.models import OutboxEventRecord
from app.db.outbox import OutboxEventType, OutboxService
from app.db.postgres import get_session
from app.indexing.neo4j_indexer import Neo4jIndexer
from app.indexing.qdrant_indexer import EntityVectorIndex, QdrantIndexer

logger = logging.getLogger(__name__)


class OutboxWorker:
    """Asynchronous worker consuming outbox mutation events and syncing downstream stores."""

    def __init__(
        self,
        qdrant_indexer: QdrantIndexer | None = None,
        neo4j_indexer: Neo4jIndexer | None = None,
        cache_invalidator: CacheInvalidator | None = None,
        entity_indexer: EntityVectorIndex | None = None,
    ) -> None:
        self.qdrant = qdrant_indexer or QdrantIndexer()
        self.neo4j = neo4j_indexer or Neo4jIndexer()
        self.cache_invalidator = cache_invalidator or CacheInvalidator()
        self.entity_indexer = entity_indexer or EntityVectorIndex()

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
                ingested_at = payload.get("ingested_at")

                owner_user_id = payload.get("owner_user_id")

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
                    ingested_at=ingested_at,
                    owner_user_id=owner_user_id,
                    properties={
                        "source_kind": payload.get("source_kind", "document"),
                        "url": payload.get("url"),
                        "fetched_at": payload.get("fetched_at"),
                    },
                )

                # 3. If extracted entities/relations are bundled with chunk
                entity_ids: list[str] = []
                for ent in payload.get("entities", []):
                    entity_id = ent.get("entity_id", ent.get("name"))
                    entity_ids.append(entity_id)
                    await self.neo4j.merge_node(
                        entity_id=entity_id,
                        name=ent.get("name", ""),
                        entity_type=ent.get("entity_type", "Concept"),
                        acl_scope=acl_scope,
                        ingested_at=ingested_at,
                        properties={
                            "doc_id": doc_id,
                            "chunk_id": chunk_id,
                            "source_id": doc_id,
                            "owner_user_id": owner_user_id or "",
                            "aliases": ent.get("aliases", []),
                            "source_kind": payload.get("source_kind", "document"),
                            "url": payload.get("url"),
                        },
                    )
                    await self.neo4j.link_chunk_entity(
                        chunk_id=chunk_id,
                        entity_id=entity_id,
                    )
                await self.neo4j.refresh_entity_props(entity_ids)

                for rel in payload.get("relations", []):
                    await self.neo4j.merge_edge(
                        source_id=rel.get("source_entity_id"),
                        target_id=rel.get("target_entity_id"),
                        relation_type=rel.get("relation_type", "RELATED_TO"),
                        acl_scope=acl_scope,
                        ingested_at=ingested_at,
                        properties={"doc_id": doc_id, "chunk_id": chunk_id},
                    )

            elif event_type == OutboxEventType.DOCUMENT_DELETED.value:
                doc_id = payload.get("doc_id", event.aggregate_id)
                await self.qdrant.delete_by_doc_id(doc_id)
                await self.neo4j.delete_by_doc_id(doc_id)
                await self._cleanup_orphan_entities(session)

            elif event_type == OutboxEventType.CHAT_GRAPH_UPSERTED.value:
                owner_user_id = payload.get("owner_user_id")
                thread_id = payload.get("thread_id", "")
                message_id = payload.get("message_id", event.aggregate_id)
                source_id = payload.get("source_id", f"chat:{message_id}")
                acl_scope = payload.get("acl_scope", {})
                ingested_at = payload.get("ingested_at")
                for ent in payload.get("entities", []):
                    entity_id = ent.get("entity_id", ent.get("name"))
                    await self.neo4j.merge_node(
                        entity_id=entity_id,
                        name=ent.get("name", ""),
                        entity_type=ent.get("entity_type", "Concept"),
                        acl_scope=acl_scope,
                        ingested_at=ingested_at,
                        properties={
                            "doc_id": "",
                            "chunk_id": "",
                            "source_id": source_id,
                            "thread_id": thread_id,
                            "message_id": message_id,
                            "owner_user_id": owner_user_id or "",
                            "source_kind": "chat",
                            "aliases": ent.get("aliases", []),
                        },
                    )
                    await self.neo4j.merge_chat_mention(
                        message_id=message_id,
                        source_id=source_id,
                        thread_id=thread_id,
                        entity_id=entity_id,
                        acl_scope=acl_scope,
                        ingested_at=ingested_at,
                        owner_user_id=owner_user_id,
                    )
                for rel in payload.get("relations", []):
                    await self.neo4j.merge_edge(
                        source_id=rel.get("source_entity_id"),
                        target_id=rel.get("target_entity_id"),
                        relation_type=rel.get("relation_type", "RELATED_TO"),
                        acl_scope=acl_scope,
                        ingested_at=ingested_at,
                        properties={
                            "doc_id": source_id,
                            "chunk_id": source_id,
                            "source_id": source_id,
                            "thread_id": thread_id,
                            "message_id": message_id,
                            "owner_user_id": owner_user_id or "",
                            "source_kind": "chat",
                        },
                    )

            elif event_type == OutboxEventType.CHAT_GRAPH_DELETED.value:
                source_id = payload.get("source_id", event.aggregate_id)
                thread_id = payload.get("thread_id")
                owner_user_id = payload.get("owner_user_id")
                await self.neo4j.delete_chat_graph(
                    source_id=source_id,
                    thread_id=thread_id,
                    owner_user_id=owner_user_id,
                )

            elif event_type == OutboxEventType.QUERY_ANSWER_UPSERTED.value:
                query_id = payload.get("query_id", event.aggregate_id)
                answer_id = payload.get("answer_id", "")
                source_kind = payload.get("source_kind", "docs")
                owner_user_id = payload.get("owner_user_id")
                acl_scope = payload.get("acl_scope", {})
                ingested_at = payload.get("ingested_at")
                query_entities = payload.get("query_entities", [])
                # Unverified answers never contribute extracted facts.
                answer_entities = (
                    payload.get("answer_entities", [])
                    if source_kind != "unverified"
                    else []
                )

                # History entities are resolved in Postgres when the answer is
                # recorded. Ensure their Neo4j nodes exist before linking the
                # Query/Answer nodes, otherwise newly resolved entities are
                # silently dropped from the graph.
                for source_id, entities in (
                    (f"chat:query:{query_id}", query_entities),
                    (f"chat:answer:{answer_id}", answer_entities),
                ):
                    for ent in entities:
                        entity_id = ent.get("entity_id") or ent.get("name")
                        if not entity_id:
                            continue
                        await self.neo4j.merge_node(
                            entity_id=entity_id,
                            name=ent.get("name") or entity_id,
                            entity_type=ent.get("entity_type") or "Concept",
                            acl_scope=acl_scope,
                            ingested_at=ingested_at,
                            properties={
                                "source_id": source_id,
                                "owner_user_id": owner_user_id or "",
                                "aliases": ent.get("aliases", []),
                                "source_kind": "chat",
                            },
                        )

                await self.neo4j.upsert_query_answer(
                    query_id=query_id,
                    answer_id=answer_id,
                    previous_query_id=payload.get("previous_query_id"),
                    thread_id=payload.get("thread_id"),
                    owner_user_id=owner_user_id,
                    raw_query=payload.get("raw_query", ""),
                    rewritten_query=payload.get("rewritten_query"),
                    answer=payload.get("answer", ""),
                    answer_policy=payload.get("answer_policy", "grounded_plus_web"),
                    source_kind=source_kind,
                    is_abstention=bool(payload.get("is_abstention", False)),
                    acl_scope=acl_scope,
                    ingested_at=ingested_at,
                    query_entities=query_entities,
                    answer_entities=answer_entities,
                    cites=payload.get("cites", []),
                    web_sources=payload.get("web_sources", []),
                )

            elif event_type == OutboxEventType.WEB_WRITE_BACK.value:
                from app.web_grounding.web_ingest import persist_web_page

                result = await persist_web_page(session=session, payload=payload)
                logger.info(
                    "Processed WEB_WRITE_BACK for %s (ingested=%s)",
                    (payload.get("page") or {}).get("url"),
                    result.ingested,
                )

            elif event_type == OutboxEventType.CACHE_INVALIDATED.value:
                summary = self.cache_invalidator.handle_outbox_event(
                    event_type=event_type,
                    payload=payload,
                )
                logger.info("Cache invalidation for doc %s: %s", payload.get("doc_id"), summary)

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

    async def _cleanup_orphan_entities(self, session: AsyncSession) -> list[str]:
        """Delete entities with no remaining mentions from Postgres and Qdrant."""
        from sqlalchemy import delete, select

        from app.db.models import EntityMentionRecord, EntityRecord

        orphan_ids = list(
            (
                await session.execute(
                    select(EntityRecord.entity_id).where(
                        ~EntityRecord.entity_id.in_(select(EntityMentionRecord.entity_id).distinct())
                    )
                )
            ).scalars().all()
        )
        if not orphan_ids:
            return []
        await session.execute(delete(EntityRecord).where(EntityRecord.entity_id.in_(orphan_ids)))
        try:
            await self.entity_indexer.delete_entities(orphan_ids)
        except Exception:
            logger.exception("Failed to delete orphan entity vectors for %s", orphan_ids)
        return orphan_ids

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
