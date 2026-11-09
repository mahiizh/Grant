import asyncio
import logging
import sys
from pathlib import Path

from app.db.postgres import announce_database_identity, get_session, verify_schema
from app.indexing.neo4j_indexer import Neo4jIndexer
from app.indexing.outbox_worker import OutboxWorker
from app.indexing.qdrant_indexer import QdrantIndexer
from app.ingestion.pipeline import IngestionPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def run_corpus_ingestion(corpus_dir: str = "corpus") -> None:
    """Ingest all markdown documents in the corpus directory into PostgreSQL and sync stores."""
    root_path = Path(__file__).resolve().parent.parent.parent.parent
    c_dir = root_path / corpus_dir

    if not c_dir.exists():
        logger.error("Corpus directory not found at: %s", c_dir)
        sys.exit(1)

    await announce_database_identity()
    await verify_schema()

    md_files = sorted(c_dir.glob("*.md"))
    print("=" * 60)
    print(f"GraphRAG Corpus Ingestion: {len(md_files)} documents found in {c_dir}")
    print("=" * 60)

    total_chunks = 0
    total_tokens = 0
    total_cost = 0.0

    for file_path in md_files:
        if file_path.name.lower() == "readme.md":
            continue

        print(f"Ingesting: {file_path.name}...")
        async with get_session() as session:
            summary = await IngestionPipeline.ingest_file(
                session=session,
                file_path=file_path,
            )
            total_chunks += summary.chunk_count
            total_tokens += summary.tokens
            total_cost += summary.cost_usd
            print(
                f"  -> {summary.chunk_count} chunks, {summary.entity_count} entities, "
                f"{summary.tokens} tokens, ${summary.cost_usd:.6f}"
            )

    # Ingest adversarial docs if present
    adv_dir = c_dir / "adversarial"
    if adv_dir.exists():
        for adv_file in sorted(adv_dir.glob("*.md")):
            print(f"Ingesting adversarial benchmark: {adv_file.name}...")
            async with get_session() as session:
                summary = await IngestionPipeline.ingest_file(
                    session=session,
                    file_path=adv_file,
                )
                total_chunks += summary.chunk_count

    # Drain Outbox to sync Qdrant and Neo4j
    print("\nSynchronizing downstream stores via Outbox Worker...")
    worker = OutboxWorker()
    processed_events = await worker.drain()
    print(f"Outbox Worker processed {processed_events} events successfully.")

    # Verification counts
    qdrant = QdrantIndexer()
    qdrant_count = await qdrant.count()

    neo4j = Neo4jIndexer()
    neo_nodes = await neo4j.count_nodes()
    neo_edges = await neo4j.count_edges()
    await neo4j.close()

    print("=" * 60)
    print("Corpus Ingestion & Multi-Store Sync Complete:")
    print(f"  Total Chunks:           {total_chunks}")
    print(f"  Qdrant Vectors:         {qdrant_count}")
    print(f"  Neo4j Entity Nodes:     {neo_nodes}")
    print(f"  Neo4j Relationship Edges:{neo_edges}")
    print(f"  Total LLM Extraction Cost: ${total_cost:.5f}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_corpus_ingestion())
