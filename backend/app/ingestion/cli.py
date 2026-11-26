import argparse
import asyncio
import logging
import sys
from pathlib import Path

from app.core.config import get_settings
from app.db.postgres import announce_database_identity, get_session, verify_schema
from app.indexing.neo4j_indexer import Neo4jIndexer
from app.indexing.outbox_worker import OutboxWorker
from app.indexing.qdrant_indexer import QdrantIndexer
from app.ingestion.corpus import iter_corpus_files
from app.ingestion.pipeline import IngestionPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def resolve_corpus_dir(corpus_dir: str | None = None) -> Path:
    """Resolve the user-supplied corpus path (CLI argument or ``CORPUS_DIR``)."""
    configured = corpus_dir or get_settings().CORPUS_DIR
    if not configured:
        raise ValueError("No corpus directory supplied. Pass --corpus-dir or set CORPUS_DIR.")
    path = Path(configured).expanduser().resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"Corpus directory not found at: {path}")
    return path


async def run_corpus_ingestion(corpus_dir: str | None = None) -> None:
    """Ingest all markdown documents in a user-supplied corpus directory."""
    try:
        c_dir = resolve_corpus_dir(corpus_dir)
    except (ValueError, FileNotFoundError) as exc:
        logger.error("%s", exc)
        sys.exit(2)

    await announce_database_identity()
    await verify_schema()

    md_files = list(iter_corpus_files(c_dir))
    print("=" * 60)
    print(f"GraphRAG Corpus Ingestion: {len(md_files)} documents found in {c_dir}")
    print("=" * 60)

    total_chunks = 0
    total_tokens = 0
    total_cost = 0.0

    for file_path in md_files:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest a user-supplied markdown corpus.")
    parser.add_argument(
        "--corpus-dir",
        default=None,
        help="Corpus directory. Defaults to CORPUS_DIR.",
    )
    args = parser.parse_args(argv)
    asyncio.run(run_corpus_ingestion(args.corpus_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
