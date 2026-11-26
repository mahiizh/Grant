import json
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
from app.evaluation.runner import diff_metrics


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


def test_load_golden_dataset(tmp_path: Path) -> None:
    rows = [
        {
            "id": "fact_001",
            "category": "fact",
            "cluster_id": "user_fact",
            "split": "test",
            "query": "What is the p99 target?",
            "expected_doc_ids": ["doc_1"],
            "optimal_strategy": "vector",
        },
        {
            "id": "multi_hop_001",
            "category": "multi_hop",
            "cluster_id": "user_multi_hop",
            "split": "test",
            "query": "What depends on the storage service?",
            "expected_doc_ids": ["doc_1", "doc_2"],
            "optimal_strategy": "graph",
        },
        {
            "id": "global_001",
            "category": "global",
            "cluster_id": "user_global",
            "split": "test",
            "query": "Summarize all service owners",
            "optimal_strategy": "hybrid",
        },
        {
            "id": "unanswerable_001",
            "category": "unanswerable",
            "cluster_id": "user_unanswerable",
            "split": "test",
            "query": "What was the company ARR?",
            "optimal_strategy": "abstain",
        },
        {
            "id": "paraphrase_001",
            "category": "paraphrase",
            "cluster_id": "user_paraphrase",
            "split": "test",
            "query": "What is the latency SLA?",
            "optimal_strategy": "cache",
        },
    ]
    golden_path = tmp_path / "questions.jsonl"
    golden_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    dataset = GoldenDataset.load_from_jsonl(golden_path)
    assert len(dataset) == 5
    assert dataset.categories == {
        "fact",
        "multi_hop",
        "global",
        "unanswerable",
        "paraphrase",
    }
    assert dataset.summary()["total"] == 5

    q = dataset.get_by_id("multi_hop_001")
    assert isinstance(q, GoldenQuestion)
    assert q.category == "multi_hop"
    assert q.optimal_strategy == "graph"
    assert q.expected_path is None
    assert q.expected_doc_ids == ["doc_1", "doc_2"]


def test_dataset_missing_file_error() -> None:
    with pytest.raises(FileNotFoundError):
        GoldenDataset.load_from_jsonl("non_existent_file.jsonl")


def test_duplicate_question_ids_are_rejected() -> None:
    question = GoldenQuestion(
        id="dup_001",
        category="fact",
        cluster_id="hand_dup_001",
        query="What is the p99 target?",
        optimal_strategy="vector",
    )
    with pytest.raises(ValueError, match="Duplicate golden question ids: dup_001"):
        GoldenDataset([question, question])


def test_duplicate_ids_across_files_are_rejected(tmp_path: Path) -> None:
    payload = (
        '{"id": "dup_002", "category": "fact", "cluster_id": "hand_dup_002", '
        '"split": "test", "query": "What is the p99 target?", '
        '"optimal_strategy": "vector"}'
    )
    (tmp_path / "a.jsonl").write_text(payload + "\n", encoding="utf-8")
    (tmp_path / "b.jsonl").write_text(payload + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate golden question ids: dup_002"):
        GoldenDataset.load_from_dir(tmp_path)


def test_paired_difference_metrics_are_retrieval_first() -> None:
    """Token F1 and answer accuracy never decide a config comparison.

    Retrieval nDCG is the primary signal. Judge correctness is added only when
    the judge actually ran; the lexical floor metrics stay diagnostic.
    """
    assert diff_metrics(judge_enabled=False) == ("chunk_ndcg@10",)
    assert diff_metrics(judge_enabled=True) == ("chunk_ndcg@10", "judge_correctness")
    for judge_enabled in (False, True):
        metrics = diff_metrics(judge_enabled=judge_enabled)
        assert "answer_f1" not in metrics
        assert "answer_accuracy" not in metrics
