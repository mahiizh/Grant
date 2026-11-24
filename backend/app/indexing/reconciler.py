import argparse
import asyncio
import logging
from typing import Any

from sqlalchemy import select

from app.db.models import ChunkRecord
from app.db.outbox import OutboxService
from app.db.postgres import announce_database_identity, get_session, verify_schema
from app.indexing.neo4j_indexer import Neo4jIndexer
from app.indexing.qdrant_indexer import QdrantIndexer

logger = logging.getLogger(__name__)


async def run_reconciliation(repair: bool = False) -> int:
    """Compare chunk IDs across Postgres, Qdrant, and Neo4j, and optionally repair drift."""
    print("=" * 60)
    print("GraphRAG Multi-Store Storage Reconciler")
    print("=" * 60)

    await announce_database_identity()
    await verify_schema()

    # 0. Keep the outbox bounded and free of duplicate pending work.
    async with get_session() as session:
        outbox_stats = await OutboxService.reconcile(session=session)
        await session.commit()
    print(
        "Outbox reconciliation:        "
        f"pruned {outbox_stats['processed_pruned']} processed, "
        f"compacted {outbox_stats['pending_compacted']} pending duplicates, "
        f"{outbox_stats['pending_remaining']} pending remain"
    )

    # 1. Fetch from PostgreSQL
    from app.db.models import EntityMentionRecord, EntityRecord

    async with get_session() as session:
        chunk_rows = list((await session.execute(select(ChunkRecord))).scalars().all())
        entity_rows = list((await session.execute(select(EntityRecord))).scalars().all())
        mention_rows = list((await session.execute(select(EntityMentionRecord))).scalars().all())

    pg_chunks: dict[str, ChunkRecord] = {r.chunk_id: r for r in chunk_rows}
    pg_ids = set(pg_chunks.keys())
    pg_entities: dict[str, EntityRecord] = {r.entity_id: r for r in entity_rows}
    pg_entity_ids = set(pg_entities.keys())
    pg_mentions = {
        (r.entity_id, r.source_id, r.source_kind): r
        for r in mention_rows
    }
    print(f"PostgreSQL (Source of Truth): {len(pg_ids)} chunks, {len(pg_entity_ids)} entities, {len(pg_mentions)} mentions")

    qdrant = QdrantIndexer()
    neo4j = Neo4jIndexer()

    try:
        # 2. Fetch from Qdrant
        qdrant_ids = await qdrant.get_all_chunk_ids()
        print(f"Qdrant Vector Store:         {len(qdrant_ids)} chunks")

        # 3. Fetch from Neo4j
        neo4j_ids = await neo4j.get_all_chunk_ids()
        async with neo4j.driver.session(database=neo4j.database) as s:
            ent_res = await s.run("MATCH (e:Entity) RETURN e.id AS id")
            neo4j_entity_ids = {str(r["id"]) for r in await ent_res.data() if r.get("id")}
            ment_res = await s.run(
                """
                MATCH (c:Chunk)-[:MENTIONS]->(e:Entity)
                RETURN e.id AS entity_id, c.doc_id AS source_id, 'document' AS source_kind
                UNION
                MATCH (m:Message)-[:MENTIONS]->(e:Entity)
                RETURN e.id AS entity_id, coalesce(m.message_id, m.id) AS source_id, 'chat' AS source_kind
                """
            )
            neo4j_mentions = {
                (str(r["entity_id"]), str(r["source_id"]), str(r.get("source_kind", "document")))
                for r in await ment_res.data()
                if r.get("entity_id") and r.get("source_id")
            }
        print(f"Neo4j Knowledge Graph:       {len(neo4j_ids)} chunks, {len(neo4j_entity_ids)} entities, {len(neo4j_mentions)} mention-edges")

        # 4. Compute Drift
        missing_qdrant = pg_ids - qdrant_ids
        missing_neo4j = pg_ids - neo4j_ids
        ghost_qdrant = qdrant_ids - pg_ids
        ghost_neo4j = neo4j_ids - pg_ids

        missing_neo4j_entities = pg_entity_ids - neo4j_entity_ids
        ghost_neo4j_entities = neo4j_entity_ids - pg_entity_ids
        missing_neo4j_mentions = set(pg_mentions.keys()) - neo4j_mentions
        ghost_neo4j_mentions = neo4j_mentions - set(pg_mentions.keys())

        has_drift = bool(
            missing_qdrant or missing_neo4j or ghost_qdrant or ghost_neo4j
            or missing_neo4j_entities or ghost_neo4j_entities
            or missing_neo4j_mentions or ghost_neo4j_mentions
        )

        print("-" * 60)
        print("Drift Analysis:")
        print(f"  Missing in Qdrant:         {len(missing_qdrant)}")
        print(f"  Missing in Neo4j:          {len(missing_neo4j)}")
        print(f"  Ghost in Qdrant:           {len(ghost_qdrant)}")
        print(f"  Ghost in Neo4j:            {len(ghost_neo4j)}")
        print(f"  Missing Neo4j entities:    {len(missing_neo4j_entities)}")
        print(f"  Ghost Neo4j entities:      {len(ghost_neo4j_entities)}")
        print(f"  Missing Neo4j mentions:    {len(missing_neo4j_mentions)}")
        print(f"  Ghost Neo4j mentions:      {len(ghost_neo4j_mentions)}")
        print("-" * 60)

        if not has_drift:
            print("[SUCCESS] All stores are in 100% synchronization. Zero drift detected.")
            return 0

        if not repair:
            print(
                "[WARNING] Drift detected! Run with `--repair` (or `make reconcile REPAIR=1`) to synchronize."
            )
            return 1

        # 5. Execute Repair
        print("[REPAIR] Repairing drift across stores...")

        for cid in missing_qdrant:
            rec = pg_chunks[cid]
            payload: dict[str, Any] = {
                "chunk_id": rec.chunk_id,
                "doc_id": rec.doc_id,
                "text": rec.text,
                "acl_scope": {
                    "tenant_id": rec.acl_tenant_id,
                    "allowed_roles": rec.acl_allowed_roles,
                    "allowed_groups": rec.acl_allowed_groups,
                    "is_public": rec.acl_is_public,
                },
                "temporal": {
                    "valid_from": rec.valid_from.isoformat() if rec.valid_from else None,
                    "valid_to": rec.valid_to.isoformat() if rec.valid_to else None,
                },
                "source_tier": rec.source_tier,
            }
            await qdrant.upsert_chunk(
                chunk_id=rec.chunk_id,
                doc_id=rec.doc_id,
                text=rec.text,
                payload=payload,
            )
            print(f"  Synced missing chunk {cid} to Qdrant.")

        for cid in missing_neo4j:
            rec = pg_chunks[cid]
            await neo4j.merge_chunk(
                chunk_id=rec.chunk_id,
                doc_id=rec.doc_id,
                text=rec.text,
                acl_scope={"tenant_id": rec.acl_tenant_id, "is_public": rec.acl_is_public},
                temporal={
                    "valid_from": rec.valid_from.isoformat() if rec.valid_from else None,
                    "valid_to": rec.valid_to.isoformat() if rec.valid_to else None,
                },
            )
            print(f"  Synced missing chunk {cid} to Neo4j.")

        for gid in ghost_qdrant:
            await qdrant.delete_chunk(gid)
            print(f"  Deleted ghost chunk {gid} from Qdrant.")

        for gid in ghost_neo4j:
            async with neo4j.driver.session(database=neo4j.database) as s:
                await s.run("MATCH (c:Chunk {chunk_id: $cid}) DETACH DELETE c", cid=gid)
            print(f"  Deleted ghost chunk {gid} from Neo4j.")

        for eid in missing_neo4j_entities:
            rec = pg_entities[eid]
            await neo4j.merge_node(
                entity_id=rec.entity_id,
                name=rec.canonical_name,
                entity_type=rec.entity_type,
                acl_scope={"tenant_id": "default", "is_public": False},
                properties={"owner_user_id": rec.owner_user_id or ""},
            )
            print(f"  Synced missing entity {eid} to Neo4j.")

        for eid in ghost_neo4j_entities:
            async with neo4j.driver.session(database=neo4j.database) as s:
                await s.run("MATCH (e:Entity {id: $eid}) DETACH DELETE e", eid=eid)
            print(f"  Deleted ghost entity {eid} from Neo4j.")

        for entity_id, source_id, source_kind in missing_neo4j_mentions:
            if source_kind == "document":
                async with neo4j.driver.session(database=neo4j.database) as s:
                    await s.run(
                        """
                        MATCH (e:Entity {id: $entity_id})
                        MATCH (c:Chunk {doc_id: $source_id})
                        MERGE (c)-[:MENTIONS]->(e)
                        """,
                        entity_id=entity_id,
                        source_id=source_id,
                    )
            else:
                async with neo4j.driver.session(database=neo4j.database) as s:
                    await s.run(
                        """
                        MATCH (e:Entity {id: $entity_id})
                        MATCH (m:Message) WHERE coalesce(m.message_id, m.id) = $source_id
                        MERGE (m)-[:MENTIONS]->(e)
                        """,
                        entity_id=entity_id,
                        source_id=source_id,
                    )
            print(f"  Synced missing mention {entity_id}<-{source_id} ({source_kind}) to Neo4j.")

        for entity_id, source_id, source_kind in ghost_neo4j_mentions:
            if source_kind == "document":
                async with neo4j.driver.session(database=neo4j.database) as s:
                    await s.run(
                        """
                        MATCH (c:Chunk {doc_id: $source_id})-[r:MENTIONS]->(e:Entity {id: $entity_id})
                        DELETE r
                        """,
                        entity_id=entity_id,
                        source_id=source_id,
                    )
            else:
                async with neo4j.driver.session(database=neo4j.database) as s:
                    await s.run(
                        """
                        MATCH (m:Message)-[r:MENTIONS]->(e:Entity {id: $entity_id})
                        WHERE coalesce(m.message_id, m.id) = $source_id
                        DELETE r
                        """,
                        entity_id=entity_id,
                        source_id=source_id,
                    )
            print(f"  Deleted ghost mention {entity_id}<-{source_id} ({source_kind}) from Neo4j.")

        print("[SUCCESS] All drift successfully repaired. Stores are now synchronized.")
        return 0

    finally:
        await qdrant.close()
        await neo4j.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-store data consistency reconciler.")
    parser.add_argument(
        "--repair", action="store_true", help="Automatically repair any detected drift."
    )
    args = parser.parse_args()

    exit_code = asyncio.run(run_reconciliation(repair=args.repair))
    exit(exit_code)


if __name__ == "__main__":
    main()
