"""Isolated evaluation harness used by ``make eval``.

The harness performs a clean corpus ingest into a dedicated PostgreSQL database
and a dedicated Qdrant collection, then scores the golden dataset against the
real production pipeline. The developer database (``POSTGRES_DB``) and the
developer collection (``QDRANT_COLLECTION``) are never touched.

Store overrides are applied *before* any other ``app.*`` import so the cached
Settings object cannot capture the developer defaults.
"""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.core.config import Settings

_BOOTSTRAP = Settings()
os.environ["POSTGRES_DB"] = _BOOTSTRAP.EVAL_POSTGRES_DB
os.environ["QDRANT_COLLECTION"] = _BOOTSTRAP.EVAL_QDRANT_COLLECTION

# Imported after the overrides above on purpose. ruff: noqa: E402
import asyncpg  # type: ignore[import-untyped]  # noqa: E402
from qdrant_client import AsyncQdrantClient, models  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.postgres import (  # noqa: E402
    announce_database_identity,
    get_engine,
    get_session,
    verify_schema,
)
from app.evaluation.datasets import GoldenDataset, SplitType  # noqa: E402
from app.evaluation.runner import BenchmarkReport, EvaluationRunner  # noqa: E402
from app.indexing.outbox_worker import OutboxWorker  # noqa: E402
from app.indexing.qdrant_indexer import QdrantIndexer  # noqa: E402
from app.ingestion.pipeline import IngestionPipeline  # noqa: E402
from app.orchestration.state import RETRIEVAL_CONFIGS, RetrievalConfig  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[3]
CORPUS_DIR = REPO_ROOT / "corpus"

EXPECTED_DOCUMENTS = 15
EXPECTED_CHUNKS = 45


def _validate_identifier(name: str) -> str:
    if not name or not all(ch.isalnum() or ch == "_" for ch in name):
        raise ValueError(f"Unsafe PostgreSQL identifier: {name!r}")
    return name


def _check_isolation() -> None:
    settings = get_settings()
    if settings.POSTGRES_DB == _BOOTSTRAP.POSTGRES_DB:
        raise RuntimeError(
            "Eval database resolves to the developer database "
            f"({settings.POSTGRES_DB!r}). Set EVAL_POSTGRES_DB to a distinct name."
        )
    if settings.QDRANT_COLLECTION == _BOOTSTRAP.QDRANT_COLLECTION:
        raise RuntimeError(
            "Eval collection resolves to the developer collection "
            f"({settings.QDRANT_COLLECTION!r}). Set EVAL_QDRANT_COLLECTION to a distinct name."
        )


async def _recreate_eval_database() -> None:
    settings = get_settings()
    db_name = _validate_identifier(settings.POSTGRES_DB)
    conn = await asyncpg.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database="postgres",
        timeout=10,
    )
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()
    print(f"Recreated eval database {db_name!r}.")


def _run_alembic_upgrade() -> None:
    """Apply Alembic migrations to the eval database in a fresh interpreter."""
    env = dict(os.environ)
    env["POSTGRES_DB"] = get_settings().POSTGRES_DB
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        check=True,
    )


async def _reset_qdrant_collection() -> None:
    settings = get_settings()
    client = AsyncQdrantClient(
        url=f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}",
        check_compatibility=False,
    )
    try:
        if await client.collection_exists(settings.QDRANT_COLLECTION):
            await client.delete_collection(settings.QDRANT_COLLECTION)
        await client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config={
                "dense": models.VectorParams(
                    size=settings.EMBEDDING_DIM,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={"sparse": models.SparseVectorParams()},
        )
    finally:
        await client.close()
    print(f"Reset eval Qdrant collection {settings.QDRANT_COLLECTION!r}.")


async def _ingest_corpus() -> None:
    if not CORPUS_DIR.exists():
        raise FileNotFoundError(f"Corpus directory not found at: {CORPUS_DIR}")

    await announce_database_identity()
    await verify_schema()

    files = sorted(CORPUS_DIR.glob("*.md"))
    adversarial = CORPUS_DIR / "adversarial"
    if adversarial.exists():
        files.extend(sorted(adversarial.glob("*.md")))

    ingested = 0
    for path in files:
        if path.name.lower() == "readme.md":
            continue
        async with get_session() as session:
            await IngestionPipeline.ingest_file(session=session, file_path=path)
        ingested += 1

    processed = await OutboxWorker().drain()
    print(f"Ingested {ingested} documents; outbox processed {processed} events.")


async def _verify_ingest() -> set[str]:
    engine = get_engine()
    async with engine.connect() as conn:
        documents = int((await conn.execute(text("select count(*) from documents"))).scalar_one())
        chunks = int((await conn.execute(text("select count(*) from chunks"))).scalar_one())
        chunk_ids = set((await conn.execute(text("select chunk_id from chunks"))).scalars().all())

    qdrant = QdrantIndexer()
    try:
        vectors = await qdrant.count()
    finally:
        await qdrant.close()

    print(f"PostgreSQL documents: {documents}")
    print(f"PostgreSQL chunks:    {chunks}")
    print(f"Qdrant vectors:       {vectors}")

    if documents != EXPECTED_DOCUMENTS:
        raise RuntimeError(f"Expected {EXPECTED_DOCUMENTS} documents, found {documents}")
    if chunks != EXPECTED_CHUNKS:
        raise RuntimeError(f"Expected {EXPECTED_CHUNKS} chunks, found {chunks}")
    if vectors != chunks:
        raise RuntimeError(f"Qdrant has {vectors} vectors but PostgreSQL has {chunks} chunks")

    return chunk_ids


def _golden_dir() -> Path:
    configured = get_settings().EVAL_GOLDEN_DIR
    return Path(configured) if configured else REPO_ROOT / "evals" / "golden"


def _load_dataset(existing_chunk_ids: set[str]) -> GoldenDataset:
    dataset = GoldenDataset.load_from_dir(_golden_dir())
    missing = dataset.missing_chunk_ids(existing_chunk_ids)
    if missing:
        detail = ", ".join(f"{question}:{chunk}" for question, chunk in missing)
        raise RuntimeError(f"Golden rows reference chunks missing after ingest: {detail}")
    print(
        f"Golden dataset: {len(dataset)} rows ({dataset.split_summary()}), "
        f"categories={sorted(dataset.categories)}"
    )
    return dataset


def _print_report(report: BenchmarkReport) -> None:
    print()
    print("=" * 88)
    print(f"Golden evaluation report (config={report.retrieval_config}, split={report.split})")
    print("=" * 88)
    print(f"Questions:        {report.total_questions}")
    print(f"Router accuracy:  {report.overall_router_accuracy:.4f}")
    print(f"Cache hit rate:   {report.cache_hit_rate:.4f}")
    print(f"Total cost:       ${report.total_cost_usd:.6f} / budget ${report.budget_usd:.4f}")
    print(f"Latency p50/p95:  {report.p50_latency_ms:.1f} ms / {report.p95_latency_ms:.1f} ms")
    print()
    header = (
        f"{'category':12s} {'n':>3s} {'chunk_r@5':>10s} {'chunk_ndcg@10':>14s} "
        f"{'chunk_mrr':>10s} {'answer_f1':>10s} {'answer_acc':>10s} "
        f"{'latency_ms':>11s} {'cost_usd':>9s}"
    )
    print(header)
    print("-" * len(header))
    for category in sorted(report.category_scores):
        scores = report.category_scores[category]
        ops = report.category_operational.get(category, {})
        count = sum(1 for row in report.per_question if row["category"] == category)
        print(
            f"{category:12s} {count:3d} "
            f"{scores.get('chunk_recall@5', 0.0):10.3f} "
            f"{scores.get('chunk_ndcg@10', 0.0):14.3f} "
            f"{scores.get('chunk_mrr', 0.0):10.3f} "
            f"{scores.get('answer_f1', 0.0):10.3f} "
            f"{scores.get('answer_accuracy', 0.0):10.3f} "
            f"{ops.get('latency_ms', 0.0):11.1f} "
            f"{ops.get('cost_usd', 0.0):9.6f}"
        )
    print("=" * 88)


def _write_json_report(report: BenchmarkReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "retrieval_config": report.retrieval_config,
        "split": report.split,
        "total_questions": report.total_questions,
        "overall_router_accuracy": report.overall_router_accuracy,
        "category_scores": report.category_scores,
        "category_operational": report.category_operational,
        "total_cost_usd": report.total_cost_usd,
        "budget_usd": report.budget_usd,
        "cache_hit_rate": report.cache_hit_rate,
        "p50_latency_ms": report.p50_latency_ms,
        "p95_latency_ms": report.p95_latency_ms,
        "summary": report.summary,
        "per_question": report.per_question,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote JSON report to {path}")


def configure_llm_cache(config: RetrievalConfig, fresh: bool = False) -> Path:
    """Point the gateway at a per-config cache directory.

    The cache key already includes the full prompt, so configs cannot poison
    each other. The separate directory makes it possible to prove a comparison
    run was cold for every configuration.
    """
    base = Path(_BOOTSTRAP.LLM_CACHE_DIR)
    cache_dir = base / f"eval-{config}"
    if fresh and cache_dir.exists():
        shutil.rmtree(cache_dir)
    os.environ["LLM_CACHE_DIR"] = str(cache_dir)
    get_settings.cache_clear()
    return cache_dir


async def prepare_eval() -> GoldenDataset:
    """Recreate and ingest the isolated eval stores, then load the golden rows."""
    _check_isolation()

    print(f"Eval PostgreSQL database: {get_settings().POSTGRES_DB}")
    print(f"Eval Qdrant collection:   {get_settings().QDRANT_COLLECTION}")

    await _recreate_eval_database()
    _run_alembic_upgrade()
    await _reset_qdrant_collection()
    await _ingest_corpus()
    existing_chunk_ids = await _verify_ingest()
    return _load_dataset(existing_chunk_ids)


async def run_config(
    dataset: GoldenDataset,
    config: RetrievalConfig,
    split: SplitType | None,
    budget_usd: float | None,
    concurrency: int | None,
) -> BenchmarkReport:
    """Run one retrieval configuration against a freshly prepared dataset."""
    orchestrator = EvaluationRunner.build_production_orchestrator()
    orchestrator.exact_cache.clear()
    orchestrator.semantic_cache.clear()
    print(f"Cleared exact and semantic caches for config={config!r}.")

    runner = EvaluationRunner(
        orchestrator=orchestrator,
        budget_usd=budget_usd,
        concurrency=concurrency,
        retrieval_config=config,
    )
    try:
        return await runner.run_benchmark(dataset, split=split)
    finally:
        await orchestrator.graph_retriever.close()


async def _run(args: argparse.Namespace) -> int:
    cache_dir = configure_llm_cache(args.config, fresh=args.fresh_llm_cache)
    print(f"LLM cache directory:      {cache_dir}")

    dataset = await prepare_eval()
    split: SplitType | None = None if args.split == "all" else args.split

    report = await run_config(
        dataset=dataset,
        config=args.config,
        split=split,
        budget_usd=args.budget_usd,
        concurrency=args.concurrency,
    )
    _print_report(report)

    if args.json_report:
        _write_json_report(report, Path(args.json_report))

    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the isolated golden evaluation.")
    parser.add_argument(
        "--split",
        choices=["dev", "test", "all"],
        default="test",
        help="Golden split to score (default: test, the CI gate split).",
    )
    parser.add_argument(
        "--config",
        choices=list(RETRIEVAL_CONFIGS),
        default="full",
        help="Retrieval ablation configuration to score (default: full).",
    )
    parser.add_argument(
        "--budget-usd",
        type=float,
        default=None,
        help="Per-run LLM budget cap. Defaults to LLM_MAX_BUDGET_PER_RUN.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="Max concurrent questions. Defaults to EVAL_CONCURRENCY.",
    )
    parser.add_argument(
        "--fresh-llm-cache",
        action="store_true",
        help="Delete this config's on-disk LLM cache before running (cold baseline).",
    )
    parser.add_argument(
        "--json-report",
        default=None,
        help="Optional path for a full JSON report.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
