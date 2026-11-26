import argparse
import asyncio
import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import DocumentRecord, EntityMentionRecord, EntityRecord
from app.db.outbox import OutboxEventType, OutboxService
from app.db.postgres import (
    DocumentRepository,
    announce_database_identity,
    get_session,
    verify_schema,
)
from app.indexing.neo4j_indexer import Neo4jIndexer
from app.indexing.outbox_worker import OutboxWorker
from app.indexing.qdrant_indexer import EntityVectorIndex, QdrantIndexer

logger = logging.getLogger(__name__)


def _print_counts(label: str, counts: dict[str, int]) -> None:
    print(
        f"{label}: "
        + ", ".join(f"{name}={value}" for name, value in sorted(counts.items()))
    )


async def _fetch_postgres() -> tuple[
    dict[str, dict[str, Any]],
    dict[str, set[str]],
    set[str],
]:
    """Return per-document snapshots, doc→entity sets, and all entity ids."""
    async with get_session() as session:
        records = list(
            (
                await session.execute(
                    select(DocumentRecord).options(selectinload(DocumentRecord.chunks))
                )
            )
            .scalars()
            .all()
        )
        entity_ids = set(
            (await session.execute(select(EntityRecord.entity_id))).scalars().all()
        )
        mentions = list((await session.execute(select(EntityMentionRecord))).scalars().all())

    documents: dict[str, dict[str, Any]] = {}
    for record in records:
        document = DocumentRepository._record_to_domain_doc(record)
        documents[record.doc_id] = {
            "document": document,
            "checksum": DocumentRepository._effective_content_hash(document),
            "chunk_ids": {chunk.chunk_id for chunk in document.chunks},
        }

    doc_entities: dict[str, set[str]] = defaultdict(set)
    for mention in mentions:
        if mention.source_kind == "document" and mention.doc_id:
            doc_entities[str(mention.doc_id)].add(str(mention.entity_id))

    return documents, dict(doc_entities), entity_ids


async def _fetch_qdrant(
    indexer: QdrantIndexer,
) -> tuple[set[str], dict[str, dict[str, dict[str, Any]]]]:
    chunk_ids = await indexer.get_all_chunk_ids()
    payloads = await indexer.get_chunks(sorted(chunk_ids))
    by_doc: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for chunk_id, payload in payloads.items():
        doc_id = payload.get("doc_id")
        if doc_id:
            by_doc[str(doc_id)][chunk_id] = payload
    return chunk_ids, dict(by_doc)


async def _fetch_neo4j(
    indexer: Neo4jIndexer,
) -> tuple[set[str], dict[str, set[str]], set[str], dict[str, int]]:
    document_ids = await indexer.get_all_document_ids()
    entity_ids = await indexer.get_all_entity_ids()
    async with indexer.driver.session(database=indexer.database) as session:
        res = await session.run(
            """
            MATCH (d:Document)-[:MENTIONS]->(e:Entity)
            RETURN d.doc_id AS doc_id, collect(e.id) AS entity_ids
            """
        )
        doc_entities = {
            str(row["doc_id"]): {str(entity_id) for entity_id in row["entity_ids"] or []}
            for row in await res.data()
            if row.get("doc_id")
        }
        node_res = await session.run("MATCH (n) RETURN count(n) AS cnt")
        node_rec = await node_res.single()
        edge_res = await session.run("MATCH ()-[r]->() RETURN count(r) AS cnt")
        edge_rec = await edge_res.single()

    counts = {
        "nodes": int(node_rec["cnt"]) if node_rec else 0,
        "edges": int(edge_rec["cnt"]) if edge_rec else 0,
    }
    return document_ids, doc_entities, entity_ids, counts


async def run_reconciliation(repair: bool = False, dry_run: bool = False) -> int:
    """Compare Neo4j/Qdrant state with Postgres and optionally re-queue repairs.

    ``--dry-run`` is strictly read-only: it skips outbox compaction, pending-event
    draining, and all repair writes.
    """
    print("=" * 60)
    print("GraphRAG Multi-Store Storage Reconciler")
    print("=" * 60)
    if dry_run:
        print("Mode: DRY RUN (no writes)")

    await announce_database_identity()
    await verify_schema()

    if not dry_run:
        # Keep the outbox bounded and free of duplicate pending work.
        async with get_session() as session:
            outbox_stats = await OutboxService.reconcile(session=session)
        print(
            "Outbox reconciliation:        "
            f"pruned {outbox_stats['processed_pruned']} processed, "
            f"compacted {outbox_stats['pending_compacted']} pending duplicates, "
            f"{outbox_stats['pending_remaining']} pending remain"
        )

    documents, pg_doc_entities, pg_entity_ids = await _fetch_postgres()
    _print_counts(
        "PostgreSQL (source of truth)",
        {
            "documents": len(documents),
            "chunks": sum(len(doc["chunk_ids"]) for doc in documents.values()),
            "entities": len(pg_entity_ids),
            "doc_entities": sum(len(values) for values in pg_doc_entities.values()),
        },
    )

    qdrant = QdrantIndexer()
    entity_index = EntityVectorIndex()
    neo4j = Neo4jIndexer()
    try:
        if not dry_run:
            # History writes are visible in Postgres immediately while downstream
            # stores are updated asynchronously. Drain before comparing so recent
            # answers do not appear as false drift.
            worker = OutboxWorker(
                qdrant_indexer=qdrant,
                neo4j_indexer=neo4j,
                entity_indexer=entity_index,
            )
            drained = await worker.drain()
            print(f"Outbox sync:                 drained {drained} pending events")

        qdrant_chunk_ids, qdrant_by_doc = await _fetch_qdrant(qdrant)
        qdrant_entity_ids = await entity_index.get_all_entity_ids()
        (
            neo4j_document_ids,
            neo4j_doc_entities,
            neo4j_entity_ids,
            neo4j_counts,
        ) = await _fetch_neo4j(neo4j)

        _print_counts(
            "Qdrant",
            {
                "chunks": len(qdrant_chunk_ids),
                "entities": len(qdrant_entity_ids),
            },
        )
        _print_counts(
            "Neo4j",
            {
                **neo4j_counts,
                "documents": len(neo4j_document_ids),
                "entities": len(neo4j_entity_ids),
                "doc_entities": sum(len(values) for values in neo4j_doc_entities.values()),
            },
        )

        drifted_docs: set[str] = set()
        missing_chunks: set[str] = set()
        ghost_chunks: set[str] = set()
        stale_checksum_chunks: set[str] = set()
        missing_doc_entities: set[str] = set()
        ghost_doc_entities: set[str] = set()

        for doc_id, snapshot in documents.items():
            q_chunks = qdrant_by_doc.get(doc_id, {})
            expected_chunks = set(snapshot["chunk_ids"])
            doc_missing_chunks = expected_chunks - set(q_chunks)
            doc_ghost_chunks = set(q_chunks) - expected_chunks
            doc_stale_chunks = {
                chunk_id
                for chunk_id in expected_chunks & set(q_chunks)
                if str(q_chunks[chunk_id].get("doc_checksum", "")) != snapshot["checksum"]
            }
            expected_entities = pg_doc_entities.get(doc_id, set())
            actual_entities = neo4j_doc_entities.get(doc_id, set())
            doc_missing_entities = expected_entities - actual_entities
            doc_ghost_entities = actual_entities - expected_entities

            if any(
                (
                    doc_missing_chunks,
                    doc_ghost_chunks,
                    doc_stale_chunks,
                    doc_missing_entities,
                    doc_ghost_entities,
                )
            ):
                drifted_docs.add(doc_id)
                missing_chunks.update(doc_missing_chunks)
                ghost_chunks.update(doc_ghost_chunks)
                stale_checksum_chunks.update(doc_stale_chunks)
                missing_doc_entities.update(doc_missing_entities)
                ghost_doc_entities.update(doc_ghost_entities)

        ghost_qdrant_doc_ids = set(qdrant_by_doc) - set(documents)
        ghost_neo4j_doc_ids = neo4j_document_ids - set(documents)
        indexed_chunk_ids = {
            chunk_id
            for doc_chunks in qdrant_by_doc.values()
            for chunk_id in doc_chunks
        }
        qdrant_chunk_ids_without_doc = qdrant_chunk_ids - indexed_chunk_ids
        missing_neo4j_entities = pg_entity_ids - neo4j_entity_ids
        ghost_neo4j_entities = neo4j_entity_ids - pg_entity_ids
        missing_qdrant_entities = pg_entity_ids - qdrant_entity_ids
        ghost_qdrant_entities = qdrant_entity_ids - pg_entity_ids

        print("-" * 60)
        print("Drift Analysis:")
        print(f"  Drifted documents:          {len(drifted_docs)}")
        print(f"  Missing Qdrant chunks:      {len(missing_chunks)}")
        print(f"  Ghost Qdrant chunks:        {len(ghost_chunks | qdrant_chunk_ids_without_doc)}")
        print(f"  Stale Qdrant checksums:     {len(stale_checksum_chunks)}")
        print(f"  Missing Neo4j doc entities: {len(missing_doc_entities)}")
        print(f"  Ghost Neo4j doc entities:   {len(ghost_doc_entities)}")
        print(f"  Ghost Qdrant documents:     {len(ghost_qdrant_doc_ids)}")
        print(f"  Ghost Neo4j documents:      {len(ghost_neo4j_doc_ids)}")
        print(f"  Missing Neo4j entities:     {len(missing_neo4j_entities)}")
        print(f"  Ghost Neo4j entities:       {len(ghost_neo4j_entities)}")
        print(f"  Missing Qdrant entities:    {len(missing_qdrant_entities)}")
        print(f"  Ghost Qdrant entities:      {len(ghost_qdrant_entities)}")
        print("-" * 60)

        has_drift = bool(
            drifted_docs
            or ghost_qdrant_doc_ids
            or ghost_neo4j_doc_ids
            or qdrant_chunk_ids_without_doc
            or missing_neo4j_entities
            or ghost_neo4j_entities
            or missing_qdrant_entities
            or ghost_qdrant_entities
        )

        if not has_drift:
            print("[SUCCESS] Zero drift detected across all stores.")
            return 0

        if dry_run:
            print("[DRY RUN] Drift detected; no writes were performed.")
            return 1
        if not repair:
            print(
                "[WARNING] Drift detected! Run with `--repair` "
                "(or `make reconcile REPAIR=1`) to re-queue index jobs."
            )
            return 1

        print("[REPAIR] Re-queuing index jobs for drifted documents...")

        for chunk_id in sorted(ghost_chunks | qdrant_chunk_ids_without_doc):
            await qdrant.delete_chunk(chunk_id)
            print(f"  Deleted ghost Qdrant chunk {chunk_id}.")

        ghost_doc_ids = ghost_qdrant_doc_ids | ghost_neo4j_doc_ids
        async with get_session() as session:
            for doc_id in sorted(drifted_docs):
                document = documents[doc_id]["document"]
                OutboxService.stage_event(
                    session=session,
                    event_type=OutboxEventType.DOCUMENT_INGESTED,
                    aggregate_type="document",
                    aggregate_id=doc_id,
                    payload=DocumentRepository._document_event_payload(
                        document, chunk_count=len(document.chunks)
                    ),
                )
                for chunk in document.chunks:
                    OutboxService.stage_event(
                        session=session,
                        event_type=OutboxEventType.CHUNK_UPSERTED,
                        aggregate_type="chunk",
                        aggregate_id=chunk.chunk_id,
                        payload=DocumentRepository._chunk_event_payload(chunk, document),
                    )
                OutboxService.stage_event(
                    session=session,
                    event_type=OutboxEventType.CACHE_INVALIDATED,
                    aggregate_type="cache",
                    aggregate_id=doc_id,
                    payload={
                        "doc_id": doc_id,
                        "reason": "reconciler_repair",
                        "owner_user_id": document.owner_user_id,
                        "shared_scope": document.acl_scope.shared_scope,
                    },
                )
                print(f"  Re-queued index jobs for {doc_id}.")

            for doc_id in sorted(ghost_doc_ids):
                q_payloads = qdrant_by_doc.get(doc_id, {})
                owner = next(
                    (
                        payload.get("owner_user_id")
                        for payload in q_payloads.values()
                        if payload.get("owner_user_id")
                    ),
                    None,
                )
                OutboxService.stage_event(
                    session=session,
                    event_type=OutboxEventType.DOCUMENT_DELETED,
                    aggregate_type="document",
                    aggregate_id=doc_id,
                    payload={"doc_id": doc_id, "owner_user_id": owner},
                )
                print(f"  Re-queued deletion for ghost document {doc_id}.")

        print("[SUCCESS] Repair jobs re-queued. Run the worker to apply them.")
        return 0
    finally:
        await qdrant.close()
        await entity_index.close()
        await neo4j.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-store data consistency reconciler.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--repair", action="store_true", help="Re-queue index jobs for drifted documents."
    )
    mode.add_argument(
        "--dry-run", action="store_true", help="Compare stores without writing anything."
    )
    args = parser.parse_args()

    exit_code = asyncio.run(
        run_reconciliation(repair=args.repair, dry_run=args.dry_run)
    )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
