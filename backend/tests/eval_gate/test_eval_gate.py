from pathlib import Path

import pytest

from app.core.config import get_settings
from app.evaluation.datasets import GoldenDataset
from app.evaluation.runner import EvaluationRunner
from tests.fakes.hermetic import (
    REPO_ROOT,
    build_hermetic_orchestrator,
    load_corpus_chunks,
)


def _golden_dir() -> Path:
    configured = get_settings().EVAL_GOLDEN_DIR
    return Path(configured) if configured else REPO_ROOT / "evals" / "golden"


@pytest.mark.anyio
async def test_golden_dataset_is_grounded_and_complete() -> None:
    """Every golden row must point at a real chunk id produced by the corpus."""
    chunks = load_corpus_chunks()
    chunk_ids = {chunk.chunk_id for chunk in chunks}
    dataset = GoldenDataset.load_from_dir(_golden_dir())

    assert len(dataset) == 30, dataset.summary()
    assert dataset.splits == {"dev", "test"}
    assert dataset.split_summary()["dev"] == 15
    assert dataset.split_summary()["test"] == 15
    assert dataset.categories == {
        "fact",
        "multi_hop",
        "global",
        "unanswerable",
        "paraphrase",
        "multi_turn",
    }
    # multi_turn.jsonl is included, not excluded.
    assert len(dataset.filter_by_category("multi_turn")) == 10

    missing = dataset.missing_chunk_ids(chunk_ids)
    assert not missing, f"Golden rows reference chunks that do not exist: {missing}"

    # Paraphrase rows must declare the parent they depend on.
    for question in dataset.filter_by_category("paraphrase"):
        assert question.depends_on, f"{question.id} has no depends_on parent"


@pytest.mark.anyio
async def test_hermetic_eval_gate_reports_chunk_level_metrics() -> None:
    """CI gate: hermetic, no network, chunk-level metrics per category."""
    dataset = GoldenDataset.load_from_dir(_golden_dir())
    orchestrator, chunks = build_hermetic_orchestrator(load_corpus_chunks())

    # No cache pre-seeding: the pipeline must earn every cache entry.
    assert orchestrator.exact_cache.stats["entries"] == 0
    assert orchestrator.semantic_cache.stats["entries"] == 0

    runner = EvaluationRunner(orchestrator=orchestrator, concurrency=2)
    report = await runner.run_benchmark(dataset, split="test")

    assert report.total_questions == 15
    assert report.split == "test"
    assert report.budget_usd > 0.0
    assert report.total_cost_usd >= 0.0
    assert len(report.per_question) == 15

    assert set(report.category_scores) == {
        "fact",
        "multi_hop",
        "global",
        "unanswerable",
        "paraphrase",
        "multi_turn",
    }
    for category, scores in report.category_scores.items():
        for metric in (
            "chunk_recall@5",
            "chunk_ndcg@10",
            "chunk_mrr",
            "chunk_hit_rate@5",
            "doc_ndcg@10",
        ):
            assert metric in scores, f"{category} missing {metric}"
        assert 0.0 <= scores["chunk_ndcg@10"] <= 1.0

    for _category, operational in report.category_operational.items():
        assert "latency_ms" in operational
        assert "cost_usd" in operational
        assert "citations_valid" in operational

    # Deterministic safety invariants (not tuned retrieval thresholds).
    assert report.category_scores["unanswerable"]["abstention_rate"] == 1.0
    assert report.category_scores["multi_turn"]["rewrite_accuracy"] >= 0.8

    # The pipeline populated the cache itself after generation.
    assert orchestrator.exact_cache.stats["entries"] > 0

    print("\nHermetic eval gate (test split)")
    print(f"  questions: {report.total_questions}")
    print(f"  router accuracy: {report.overall_router_accuracy:.4f}")
    print(f"  cache hit rate: {report.cache_hit_rate:.4f}")
    print(f"  cost: ${report.total_cost_usd:.6f} / budget ${report.budget_usd:.2f}")
    for category in sorted(report.category_scores):
        scores = report.category_scores[category]
        print(
            f"  {category:12s} chunk_recall@5={scores['chunk_recall@5']:.3f} "
            f"chunk_ndcg@10={scores['chunk_ndcg@10']:.3f} "
            f"chunk_mrr={scores['chunk_mrr']:.3f}"
        )
