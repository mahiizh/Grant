import argparse
import asyncio
import logging
from typing import Any

from sqlalchemy import select

from app.db.models import ChunkRecord
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

    # 1. Fetch from PostgreSQL
    async with get_session() as session:
        stmt = select(ChunkRecord)
        result = await session.execute(stmt)
        pg_records = list(result.scalars().all())

    pg_chunks: dict[str, ChunkRecord] = {r.chunk_id: r for r in pg_records}
    pg_ids = set(pg_chunks.keys())
    print(f"PostgreSQL (Source of Truth): {len(pg_ids)} chunks")

    qdrant = QdrantIndexer()
    neo4j = Neo4jIndexer()

    try:
        # 2. Fetch from Qdrant
        qdrant_ids = await qdrant.get_all_chunk_ids()
        print(f"Qdrant Vector Store:         {len(qdrant_ids)} chunks")

        # 3. Fetch from Neo4j
        neo4j_ids = await neo4j.get_all_chunk_ids()
        print(f"Neo4j Knowledge Graph:       {len(neo4j_ids)} chunks")

        # 4. Compute Drift
        missing_qdrant = pg_ids - qdrant_ids
        missing_neo4j = pg_ids - neo4j_ids
        ghost_qdrant = qdrant_ids - pg_ids
        ghost_neo4j = neo4j_ids - pg_ids

        has_drift = bool(missing_qdrant or missing_neo4j or ghost_qdrant or ghost_neo4j)

        print("-" * 60)
        print("Drift Analysis:")
        print(f"  Missing in Qdrant: {len(missing_qdrant)}")
        print(f"  Missing in Neo4j:  {len(missing_neo4j)}")
        print(f"  Ghost in Qdrant:   {len(ghost_qdrant)}")
        print(f"  Ghost in Neo4j:    {len(ghost_neo4j)}")
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

        # Fix Qdrant missing
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

        # Fix Neo4j missing
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

        # Fix Qdrant ghosts
        for gid in ghost_qdrant:
            await qdrant.delete_chunk(gid)
            print(f"  Deleted ghost chunk {gid} from Qdrant.")

        # Fix Neo4j ghosts
        for gid in ghost_neo4j:
            async with neo4j.driver.session() as s:
                await s.run("MATCH (c:Chunk {chunk_id: $cid}) DETACH DELETE c", cid=gid)
            print(f"  Deleted ghost chunk {gid} from Neo4j.")

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
