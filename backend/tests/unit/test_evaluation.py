from pathlib import Path

import pytest

from app.evaluation.datasets import GoldenDataset, GoldenQuestion
from app.evaluation.retrieval_metrics import (
    evaluate_retrieval,
    hit_rate_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_recall_at_k() -> None:
    targets = {"doc_1", "doc_2"}
    retrieved = ["doc_1", "doc_3", "doc_2", "doc_4"]

    assert recall_at_k(retrieved, targets, k=1) == 0.5
    assert recall_at_k(retrieved, targets, k=2) == 0.5
    assert recall_at_k(retrieved, targets, k=3) == 1.0
    assert recall_at_k(retrieved, targets, k=10) == 1.0

    # No hits
    assert recall_at_k(["doc_x", "doc_y"], targets, k=2) == 0.0

    # Empty targets (e.g. unanswerable)
    assert recall_at_k([], set(), k=5) == 1.0
    assert recall_at_k(["doc_1"], set(), k=5) == 0.0


def test_precision_at_k() -> None:
    targets = {"doc_1", "doc_2"}
    retrieved = ["doc_1", "doc_3", "doc_2", "doc_4"]

    assert precision_at_k(retrieved, targets, k=1) == 1.0
    assert precision_at_k(retrieved, targets, k=2) == 0.5
    assert precision_at_k(retrieved, targets, k=4) == 0.5

    # Zero hits
    assert precision_at_k(["doc_x", "doc_y"], targets, k=2) == 0.0


def test_reciprocal_rank() -> None:
    targets = {"doc_target"}

    assert reciprocal_rank(["doc_target", "doc_other"], targets) == 1.0
    assert reciprocal_rank(["doc_other", "doc_target"], targets) == 0.5
    assert reciprocal_rank(["a", "b", "c", "doc_target"], targets) == 0.25
    assert reciprocal_rank(["a", "b", "c"], targets) == 0.0


def test_hit_rate_at_k() -> None:
    targets = {"doc_1"}
    retrieved = ["doc_other", "doc_1", "doc_3"]

    assert hit_rate_at_k(retrieved, targets, k=1) == 0.0
    assert hit_rate_at_k(retrieved, targets, k=2) == 1.0
    assert hit_rate_at_k(retrieved, targets, k=3) == 1.0


def test_ndcg_at_k() -> None:
    targets = {"doc_1"}

    # Perfect rank: doc_1 is at rank 1
    assert ndcg_at_k(["doc_1", "doc_2"], targets, k=2) == 1.0

    # Displaced rank: doc_1 is at rank 2
    # DCG = 1 / log2(3) ≈ 0.6309, IDCG = 1 / log2(2) = 1.0
    score = ndcg_at_k(["doc_2", "doc_1"], targets, k=2)
    assert 0.63 < score < 0.64

    # No relevant items in top-k
    assert ndcg_at_k(["doc_2", "doc_3"], targets, k=2) == 0.0


def test_evaluate_retrieval_aggregate() -> None:
    targets = {"doc_1", "doc_2"}
    retrieved = ["doc_1", "doc_x", "doc_2"]

    results = evaluate_retrieval(retrieved, targets, k_values=(1, 3))
    assert "mrr" in results
    assert "recall@1" in results
    assert "recall@3" in results
    assert "precision@1" in results
    assert "precision@3" in results
    assert "ndcg@1" in results
    assert "ndcg@3" in results
    assert "hit_rate@1" in results
    assert "hit_rate@3" in results

    assert results["mrr"] == 1.0
    assert results["recall@1"] == 0.5
    assert results["recall@3"] == 1.0
    assert results["hit_rate@1"] == 1.0


def test_load_golden_dataset() -> None:
    # Locate evals/golden/questions.jsonl from repo root
    repo_root = Path(__file__).resolve().parents[3]
    golden_path = repo_root / "evals" / "golden" / "questions.jsonl"
    assert golden_path.exists(), f"Expected golden dataset file at {golden_path}"

    dataset = GoldenDataset.load_from_jsonl(golden_path)
    assert len(dataset) == 20

    # Verify all 5 categories are covered
    expected_categories = {"fact", "multi_hop", "global", "unanswerable", "paraphrase"}
    assert dataset.categories == expected_categories

    # Verify summary
    summary = dataset.summary()
    assert summary["total"] == 20
    assert summary["fact"] == 6
    assert summary["multi_hop"] == 4
    assert summary["global"] == 2
    assert summary["unanswerable"] == 4
    assert summary["paraphrase"] == 4

    # Verify specific lookup
    q = dataset.get_by_id("multi_hop_001")
    assert isinstance(q, GoldenQuestion)
    assert q.category == "multi_hop"
    assert q.optimal_strategy == "graph"
    assert q.expected_path is None
    assert len(q.expected_doc_ids) >= 2


def test_dataset_missing_file_error() -> None:
    with pytest.raises(FileNotFoundError):
        GoldenDataset.load_from_jsonl("non_existent_file.jsonl")
