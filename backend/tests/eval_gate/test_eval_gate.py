from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base
from app.evaluation import EvaluationRunner, GoldenDataset


@pytest.fixture
async def test_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated, in-memory SQLite database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.anyio
async def test_golden_benchmark_ci_eval_gate(test_session: AsyncSession) -> None:
    """CI Evaluation Gate: Enforces quality, recall, and safety thresholds on the golden dataset.

    Fails the build if retrieval accuracy or unanswerable abstention degrades.
    """
    repo_root = Path(__file__).resolve().parents[3]
    corpus_dir = repo_root / "corpus"
    golden_file = repo_root / "evals" / "golden" / "questions.jsonl"

    assert golden_file.exists(), f"Golden dataset missing at {golden_file}"

    # 1. Setup Corpus, Ingestion, and Orchestrator
    orchestrator = await EvaluationRunner.setup_corpus_and_orchestrator(
        session=test_session,
        corpus_dir=corpus_dir,
    )
    await test_session.flush()

    # 2. Load the 20-Question Golden Benchmark
    dataset = GoldenDataset.load_from_jsonl(golden_file)
    assert len(dataset) == 20

    # 3. Run Benchmark
    runner = EvaluationRunner(orchestrator=orchestrator)
    report = await runner.run_benchmark(dataset)

    scores = report.category_scores

    # 4. Enforce Quality Gate Thresholds (Definition of Done)
    # Threshold 1: Router accuracy must be >= 85%
    assert report.overall_router_accuracy >= 0.85, (
        f"Router accuracy dropped below 85%: {report.overall_router_accuracy:.2%}"
    )

    # Threshold 2: Unanswerable queries MUST abstain with 100% precision (Zero Hallucinations)
    unans_rate = scores["unanswerable"]["abstention_rate"]
    assert unans_rate == 1.0, f"Abstention rate dropped below 100%: {unans_rate:.2%}"

    # Threshold 3: Fact retrieval Recall@1 must be >= 80%
    fact_r1 = scores["fact"]["recall@1"]
    assert fact_r1 >= 0.80, f"Fact Recall@1 dropped below 80%: {fact_r1:.2%}"

    # Threshold 4: Fact retrieval nDCG@1 must be >= 80%
    fact_ndcg1 = scores["fact"]["ndcg@1"]
    assert fact_ndcg1 >= 0.80, f"Fact nDCG@1 dropped below 80%: {fact_ndcg1:.2%}"

    # Threshold 5: Multi-hop retrieval Recall@3 must be >= 80%
    multihop_r3 = scores["multi_hop"]["recall@3"]
    assert multihop_r3 >= 0.80, f"Multi-hop Recall@3 dropped below 80%: {multihop_r3:.2%}"

    # Threshold 6: Cache hit rate on paraphrases must be >= 80%
    cache_rate = scores["paraphrase"]["cache_hit_rate"]
    assert cache_rate >= 0.80, f"Cache hit rate dropped below 80%: {cache_rate:.2%}"
