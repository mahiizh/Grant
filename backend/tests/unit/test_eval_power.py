"""Unit tests for the item-6 evaluation power additions."""

import json
import os

import pytest

from app.evaluation.bootstrap import (
    bootstrap_interval,
    cluster_bootstrap_interval,
    cluster_paired_bootstrap_difference,
    cluster_paired_bootstrap_sd,
    paired_bootstrap_difference,
    paired_sd,
)
from app.evaluation.calibration import cohen_kappa, load_agreement
from app.evaluation.datasets import GoldenDataset, GoldenQuestion
from app.evaluation.judge import JudgeVerdict
from app.evaluation.runner import EvaluationRunner
from app.orchestration.condense import condense_query
from tests.fakes.fake_gateway import FakeModelGateway
from tests.fakes.hermetic import REPO_ROOT, build_hermetic_orchestrator, load_corpus_chunks


def test_bootstrap_interval_is_deterministic_and_brackets_the_mean() -> None:
    values = [0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 1.0, 1.0]
    first = bootstrap_interval(values, iterations=500, seed=7)
    second = bootstrap_interval(values, iterations=500, seed=7)

    assert first == second
    assert first.n == len(values)
    assert 0.0 <= first.low <= first.mean <= first.high <= 1.0


def test_paired_difference_uses_aligned_observations() -> None:
    left = [1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 1.0]
    right = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    interval = paired_bootstrap_difference(left, right, iterations=500, seed=11)

    assert interval.n == len(left)
    assert interval.mean == pytest.approx(0.75)
    assert interval.low > 0.0


def test_cluster_bootstrap_reports_effective_cluster_count() -> None:
    values = [1.0, 1.0, 0.0, 0.0]
    clusters = ["template_a", "template_a", "template_b", "template_b"]
    first = cluster_bootstrap_interval(values, clusters, iterations=500, seed=7)
    second = cluster_bootstrap_interval(values, clusters, iterations=500, seed=7)

    assert first == second
    assert first.n == 2  # clusters, not the four rows
    assert first.mean == pytest.approx(0.5)
    with pytest.raises(ValueError, match="same length"):
        cluster_bootstrap_interval(values, clusters[:1])


def test_cluster_paired_difference_and_bootstrap_sd() -> None:
    left = [1.0, 1.0, 0.0, 0.0]
    right = [0.0, 0.0, 0.0, 0.0]
    clusters = ["doc_a", "doc_a", "doc_b", "doc_b"]

    interval = cluster_paired_bootstrap_difference(left, right, clusters, iterations=500, seed=11)
    sd = cluster_paired_bootstrap_sd(left, right, clusters, iterations=500, seed=11)

    assert interval.n == 2
    assert interval.mean == pytest.approx(0.5)
    assert sd > 0.0
    assert paired_sd(left, right) == pytest.approx(0.5774, abs=0.0001)


def test_cohen_kappa_matches_known_values() -> None:
    assert cohen_kappa([1, 1, 0, 0], [1, 1, 0, 0]) == 1.0
    assert cohen_kappa([1, 1, 0, 0], [0, 0, 1, 1]) == -1.0
    # 75% agreement, chance agreement 50% -> kappa 0.5
    assert cohen_kappa([1, 1, 1, 0], [1, 1, 0, 0]) == pytest.approx(0.5)


def test_deepeval_env_guard_restores_litellm_api_base(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.evaluation.judge import _PLACEHOLDER_API_BASE, _deepeval_settings_guard

    monkeypatch.delenv("LITELLM_API_BASE", raising=False)
    with _deepeval_settings_guard():
        assert os.environ["LITELLM_API_BASE"] == _PLACEHOLDER_API_BASE
    # Leaving the placeholder behind would route real LiteLLM calls to localhost.
    assert "LITELLM_API_BASE" not in os.environ


def test_calibration_set_is_balanced_and_complete() -> None:
    path = REPO_ROOT / "evals" / "calibration" / "judge_answers.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 30
    labels = [int(row["human_label"]) for row in rows]
    assert labels.count(1) == 15
    assert labels.count(0) == 15
    assert all(row["question"] and row["answer"] and row["reference"] for row in rows)
    # The committed agreement file is optional; the report must handle its absence.
    assert load_agreement() is None or load_agreement().n == 30  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_condense_resolves_generated_camelcase_services() -> None:
    rewritten, _ = await condense_query(
        "What is its p99 latency SLA?",
        history=[
            {"role": "user", "content": "What is the p99 latency SLA for EventStream?"},
            {"role": "assistant", "content": "EventStream targets a p99 latency of 33ms."},
        ],
    )
    assert rewritten == "What is EventStream's p99 latency SLA?"

    # The legacy "outbox" keyword must not swallow the generated OutboxWorker name.
    rewritten, _ = await condense_query(
        "What is its p99 latency SLA?",
        history=[
            {"role": "user", "content": "What is the p99 latency SLA for OutboxWorker?"},
            {"role": "assistant", "content": "OutboxWorker targets a p99 latency of 47ms."},
        ],
    )
    assert rewritten == "What is OutboxWorker's p99 latency SLA?"


class FakeJudge:
    """Deterministic judge used to test runner wiring without a provider call."""

    def __init__(self) -> None:
        self.model_name = "fake-judge"
        self.threshold = 0.5
        self.calls = 0

    async def evaluate(
        self,
        *,
        question: str,
        answer: str,
        expected_answer: str | None,
        context: list[str] | None = None,
    ) -> JudgeVerdict:
        self.calls += 1
        return JudgeVerdict(
            correctness_score=1.0,
            correctness_pass=True,
            faithfulness_score=1.0,
            faithfulness_pass=True,
            correctness_reason="fake",
            faithfulness_reason="fake",
        )


@pytest.mark.anyio
async def test_runner_attaches_judge_metrics_and_intervals() -> None:
    legacy = GoldenDataset.load_from_jsonl(REPO_ROOT / "evals" / "golden" / "questions.jsonl")
    question = legacy.get_by_id("fact_001")
    assert question is not None
    dataset = GoldenDataset([GoldenQuestion.model_validate(question.model_dump())])

    chunks = [chunk for chunk in load_corpus_chunks() if chunk.doc_id == "doc_rfc_001"]
    orchestrator, _ = build_hermetic_orchestrator(chunks)
    judge = FakeJudge()
    runner = EvaluationRunner(orchestrator=orchestrator, judge=judge)  # type: ignore[arg-type]
    report = await runner.run_benchmark(dataset, split="dev")

    assert judge.calls == 1
    assert report.judge_model == "fake-judge"
    assert report.judge_threshold == 0.5
    assert report.category_scores["fact"]["judge_correctness"] == 1.0
    assert report.category_scores["fact"]["judge_faithfulness"] == 1.0
    assert report.category_scores["fact"]["judge_pass_rate"] == 1.0
    assert report.overall_intervals["judge_correctness"]["n"] == 1
    assert report.per_question[0]["judge"]["correctness_pass"] is True
    assert report.per_question[0]["retrieved_context"]


@pytest.mark.anyio
async def test_runner_propagates_retrieval_only_mode() -> None:
    legacy = GoldenDataset.load_from_jsonl(REPO_ROOT / "evals" / "golden" / "questions.jsonl")
    question = legacy.get_by_id("fact_001")
    assert question is not None
    dataset = GoldenDataset([GoldenQuestion.model_validate(question.model_dump())])
    chunks = [chunk for chunk in load_corpus_chunks() if chunk.doc_id == "doc_rfc_001"]
    orchestrator, _ = build_hermetic_orchestrator(chunks)
    runner = EvaluationRunner(orchestrator=orchestrator, retrieval_only=True)

    report = await runner.run_benchmark(dataset, split="dev")

    assert report.retrieval_only is True
    assert all(row["answer"] == "" for row in report.per_question)
    assert report.per_question[0]["chunk_metrics"]["chunk_recall@5"] >= 0.0


def test_fake_gateway_is_still_importable() -> None:
    # Guards the FakeJudge construction pattern used above.
    assert FakeModelGateway().default_model == "mock-hermetic"


def test_generated_golden_rows_are_grounded() -> None:
    chunks = load_corpus_chunks()
    chunk_ids = {chunk.chunk_id for chunk in chunks}
    dataset = GoldenDataset.load_from_dir(REPO_ROOT / "evals" / "golden")
    assert not dataset.missing_chunk_ids(chunk_ids)
    assert dataset.split_summary()["test"] >= 120


def test_every_golden_row_has_a_resampling_cluster() -> None:
    dataset = GoldenDataset.load_from_dir(REPO_ROOT / "evals" / "golden")
    rows = dataset.questions
    assert len(rows) == 240
    assert len({row.cluster_id for row in rows}) >= 15
    for row in rows:
        assert row.cluster_id
        if row.id.startswith("gen_"):
            assert row.cluster_id.startswith("gen_")
        elif row.expected_doc_ids:
            assert row.cluster_id == row.expected_doc_ids[0]
        else:
            assert row.cluster_id == f"hand_{row.id}"
