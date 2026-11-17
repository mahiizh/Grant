import asyncio
import math
import subprocess
from dataclasses import dataclass, field
from typing import Any

from app.cache.exact import ExactCache
from app.cache.semantic import SemanticCache
from app.core.acl import ACLScope
from app.core.config import get_settings
from app.evaluation.answer_metrics import answer_accuracy
from app.evaluation.bootstrap import bootstrap_interval
from app.evaluation.datasets import GoldenDataset, GoldenQuestion, SplitType
from app.evaluation.judge import AnswerJudge
from app.evaluation.retrieval_metrics import (
    hit_rate_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from app.evaluation.router_regret import evaluate_router_decisions
from app.graph.retrievers import GraphRetriever
from app.llm.gateway import BudgetExceededError, ModelGateway
from app.orchestration.state import RAGState, RetrievalConfig
from app.orchestration.workflow import RAGOrchestrator
from app.retrieval.hybrid import HybridRetriever


def percentile(values: list[float], fraction: float) -> float:
    """Return a linearly interpolated percentile (``fraction`` in ``[0, 1]``)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 2)
    weight = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * weight, 2)


@dataclass
class BenchmarkReport:
    """Consolidated benchmark results across the evaluation categories."""

    total_questions: int
    overall_router_accuracy: float
    split: str = "all"
    retrieval_config: str = "full"
    git_sha: str | None = None
    category_scores: dict[str, dict[str, float]] = field(default_factory=dict)
    category_operational: dict[str, dict[str, float]] = field(default_factory=dict)
    per_question: list[dict[str, Any]] = field(default_factory=list)
    total_cost_usd: float = 0.0
    budget_usd: float = 0.0
    cache_hit_rate: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    retrieval_p50_latency_ms: float = 0.0
    retrieval_p95_latency_ms: float = 0.0
    category_intervals: dict[str, dict[str, dict[str, float | int]]] = field(default_factory=dict)
    overall_intervals: dict[str, dict[str, float | int]] = field(default_factory=dict)
    judge_model: str | None = None
    judge_threshold: float | None = None
    summary: dict[str, Any] = field(default_factory=dict)


# Metrics that get a bootstrap interval in every report. Retrieval quality is
# primary. Answer accuracy and token F1 are secondary floor metrics: lexical
# overlap can rise while answers get worse, so neither decides a comparison.
INTERVAL_METRICS = (
    "chunk_recall@5",
    "chunk_ndcg@10",
    "chunk_mrr",
    "answer_accuracy",
    "answer_f1",
)
JUDGE_METRICS = ("judge_correctness", "judge_faithfulness", "judge_pass_rate")

# Metrics in the paired config-vs-baseline difference table. Retrieval nDCG is
# the primary comparison; judge correctness joins it only when the judge ran.
# Token F1 and answer accuracy stay out: they are diagnostics, not evidence that
# one configuration beats another.
PRIMARY_DIFF_METRICS = ("chunk_ndcg@10",)


def diff_metrics(judge_enabled: bool) -> tuple[str, ...]:
    """Return the metrics shown in the paired difference table."""
    if judge_enabled:
        return PRIMARY_DIFF_METRICS + ("judge_correctness",)
    return PRIMARY_DIFF_METRICS


class EvaluationRunner:
    """Executes the benchmark suite against the GraphRAG orchestrator and scores IR metrics."""

    def __init__(
        self,
        orchestrator: RAGOrchestrator | None = None,
        budget_usd: float | None = None,
        concurrency: int | None = None,
        retrieval_config: RetrievalConfig = "full",
        judge: AnswerJudge | None = None,
    ) -> None:
        self.orchestrator = orchestrator or RAGOrchestrator()
        self.retrieval_config = retrieval_config
        self.judge = judge
        settings = get_settings()
        self.budget_usd = budget_usd if budget_usd is not None else settings.LLM_MAX_BUDGET_PER_RUN
        self.concurrency = max(
            1, concurrency if concurrency is not None else settings.EVAL_CONCURRENCY
        )

    @classmethod
    def build_production_orchestrator(cls, cache_enabled: bool = True) -> RAGOrchestrator:
        """Build the live orchestrator.

        Caches are deliberately *not* pre-seeded. The eval CLI clears them at the
        start of a run so every answer is earned by the pipeline under test.
        Comparison runs pass ``cache_enabled=False`` so a hit cannot return an
        answer produced by another retrieval configuration.
        """
        return RAGOrchestrator(
            hybrid_retriever=HybridRetriever(),
            graph_retriever=GraphRetriever(),
            exact_cache=ExactCache(),
            semantic_cache=SemanticCache(similarity_threshold=0.75),
            model_gateway=ModelGateway(max_budget_per_run=get_settings().LLM_MAX_BUDGET_PER_RUN),
            cache_enabled=cache_enabled,
        )

    @staticmethod
    def _ordered_waves(questions: list[GoldenQuestion]) -> list[list[GoldenQuestion]]:
        """Group questions into dependency waves so parents run before paraphrases."""
        by_id = {q.id: q for q in questions}
        remaining = dict(by_id)
        completed: set[str] = set()
        waves: list[list[GoldenQuestion]] = []

        while remaining:
            wave = [
                q
                for q in remaining.values()
                if all(dep in completed or dep not in by_id for dep in q.depends_on)
            ]
            if not wave:
                unresolved = ", ".join(sorted(remaining))
                raise ValueError(f"Unresolved or cyclic golden dependencies: {unresolved}")
            waves.append(wave)
            for q in wave:
                remaining.pop(q.id)
                completed.add(q.id)

        return waves

    @staticmethod
    def _rewrite_accuracy(question: GoldenQuestion, rewritten: str) -> float:
        if question.category != "multi_turn":
            return 0.0
        if not question.expected_entities:
            return 1.0
        lowered = rewritten.lower()
        return 1.0 if all(ent.lower() in lowered for ent in question.expected_entities) else 0.0

    @staticmethod
    def _score_question(
        question: GoldenQuestion,
        state: RAGState,
    ) -> dict[str, Any]:
        evidence = state.get("evidence", [])
        retrieved_chunk_ids = [ev.chunk_id for ev in evidence]
        retrieved_doc_ids = list(dict.fromkeys(ev.doc_id for ev in evidence))

        target_chunks = set(question.expected_chunk_ids)
        target_docs = set(question.expected_doc_ids)

        chunk_metrics = {
            "chunk_recall@1": recall_at_k(retrieved_chunk_ids, target_chunks, 1),
            "chunk_recall@3": recall_at_k(retrieved_chunk_ids, target_chunks, 3),
            "chunk_recall@5": recall_at_k(retrieved_chunk_ids, target_chunks, 5),
            "chunk_precision@1": precision_at_k(retrieved_chunk_ids, target_chunks, 1),
            "chunk_ndcg@5": ndcg_at_k(retrieved_chunk_ids, target_chunks, 5),
            "chunk_ndcg@10": ndcg_at_k(retrieved_chunk_ids, target_chunks, 10),
            "chunk_mrr": reciprocal_rank(retrieved_chunk_ids, target_chunks),
            "chunk_hit_rate@5": hit_rate_at_k(retrieved_chunk_ids, target_chunks, 5),
        }
        doc_metrics = {
            "doc_recall@3": recall_at_k(retrieved_doc_ids, target_docs, 3),
            "doc_ndcg@10": ndcg_at_k(retrieved_doc_ids, target_docs, 10),
            "doc_mrr": reciprocal_rank(retrieved_doc_ids, target_docs),
        }

        rewritten = state.get("rewritten_query", question.query)
        operational = {
            "latency_ms": float(state.get("latency_ms", 0.0)),
            "retrieval_latency_ms": float(state.get("retrieval_latency_ms", 0.0)),
            "cost_usd": float(state.get("cost_usd", 0.0)),
            "is_cached": 1.0 if state.get("is_cached", False) else 0.0,
            "is_abstention": 1.0 if state.get("is_abstention", False) else 0.0,
            "citations_valid": 1.0 if state.get("citations_valid", False) else 0.0,
            "rewrite_accuracy": EvaluationRunner._rewrite_accuracy(question, rewritten),
        }

        answer_f1, answer_correct = answer_accuracy(
            prediction=state.get("answer", ""),
            reference=question.expected_answer,
            is_abstention=bool(state.get("is_abstention", False)),
        )
        answer_metrics = {
            "answer_f1": answer_f1,
            "answer_accuracy": answer_correct,
        }

        return {
            "id": question.id,
            "category": question.category,
            "split": question.split,
            "query": question.query,
            "expected_answer": question.expected_answer,
            "route": state.get("route", "vector"),
            "optimal_strategy": question.optimal_strategy,
            "rewritten_query": rewritten,
            "answer": state.get("answer", ""),
            "retrieved_chunk_ids": retrieved_chunk_ids,
            "retrieved_doc_ids": retrieved_doc_ids,
            "retrieved_context": [ev.text for ev in evidence],
            "evidence_details": [
                {
                    "chunk_id": ev.chunk_id,
                    "score": ev.score,
                    "method": ev.retrieval_method,
                    "path": ev.path,
                }
                for ev in evidence
            ],
            "expected_chunk_ids": sorted(target_chunks),
            "expected_doc_ids": sorted(target_docs),
            "chunk_metrics": chunk_metrics,
            "doc_metrics": doc_metrics,
            "answer_metrics": answer_metrics,
            "operational": operational,
        }

    async def run_benchmark(
        self,
        dataset: GoldenDataset,
        split: SplitType | None = None,
    ) -> BenchmarkReport:
        """Execute the golden questions and compute chunk-level IR metrics per category."""
        selected = dataset.filter_by_split(split) if split else dataset
        questions = selected.questions
        if not questions:
            raise ValueError(f"No golden questions selected for split={split!r}")

        gateway = self.orchestrator.gateway
        gateway.max_run_budget = self.budget_usd
        gateway.reset_usage()

        admin_scope = ACLScope.restricted(
            allowed_roles={
                "admin",
                "data-platform",
                "payments",
                "core-banking",
                "sre",
                "executive-audit",
                "security",
                "ml-platform",
                "customer-support",
                "treasury",
                "risk",
                "compliance",
            },
            allowed_groups={"platform-admins"},
        )

        router_predictions: list[tuple[str, str]] = []
        per_question: list[dict[str, Any]] = []
        semaphore = asyncio.Semaphore(self.concurrency)

        async def run_one(question: GoldenQuestion) -> dict[str, Any]:
            async with semaphore:
                if gateway.total_spent_usd >= self.budget_usd:
                    raise BudgetExceededError(
                        f"Run budget ${self.budget_usd:.4f} exhausted before question "
                        f"{question.id} (spent ${gateway.total_spent_usd:.6f})"
                    )
                state = await self.orchestrator.run(
                    query=question.query,
                    thread_history=question.thread_turns,
                    acl_scope=admin_scope,
                    retrieval_config=self.retrieval_config,
                )
                return self._score_question(question, state)

        for wave in self._ordered_waves(questions):
            results = await asyncio.gather(*(run_one(q) for q in wave))
            per_question.extend(results)

        # Preserve dataset order in the report even though waves ran concurrently.
        order = {q.id: index for index, q in enumerate(questions)}
        per_question.sort(key=lambda row: order[row["id"]])

        judge = self.judge
        if judge is not None:
            judge_semaphore = asyncio.Semaphore(self.concurrency)

            async def judge_one(row: dict[str, Any]) -> None:
                async with judge_semaphore:
                    verdict = await judge.evaluate(
                        question=str(row["query"]),
                        answer=str(row["answer"]),
                        expected_answer=row["expected_answer"],
                        context=list(row["retrieved_context"]),
                    )
                row["judge"] = verdict.as_dict()

            await asyncio.gather(*(judge_one(row) for row in per_question))

        for row in per_question:
            router_predictions.append((row["route"], row["optimal_strategy"]))

        category_scores: dict[str, dict[str, float]] = {}
        category_operational: dict[str, dict[str, float]] = {}
        category_judge: dict[str, dict[str, float]] = {}
        for row in per_question:
            category = row["category"]
            category_scores.setdefault(category, {}).setdefault("_count", 0.0)
            category_operational.setdefault(category, {}).setdefault("_count", 0.0)
            category_judge.setdefault(category, {}).setdefault("_count", 0.0)

        for row in per_question:
            category = row["category"]
            metrics = {**row["chunk_metrics"], **row["doc_metrics"], **row["answer_metrics"]}
            operational = dict(row["operational"])
            if category == "unanswerable":
                metrics["abstention_rate"] = operational["is_abstention"]
            if category == "paraphrase":
                metrics["cache_hit_rate"] = operational["is_cached"]
            if category == "multi_turn":
                metrics["rewrite_accuracy"] = operational["rewrite_accuracy"]

            scores = category_scores[category]
            for name, value in metrics.items():
                scores[name] = scores.get(name, 0.0) + value
            scores["_count"] += 1

            ops = category_operational[category]
            for name, value in operational.items():
                ops[name] = ops.get(name, 0.0) + value
            ops["_count"] += 1

            judge_metrics = _judge_metrics(row)
            if judge_metrics:
                judge_scores = category_judge[category]
                for name, value in judge_metrics.items():
                    judge_scores[name] = judge_scores.get(name, 0.0) + value
                judge_scores["_count"] += 1

        def finalize(groups: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
            finalized: dict[str, dict[str, float]] = {}
            for category, values in groups.items():
                count = values["_count"]
                finalized[category] = {
                    name: round(total / count, 4)
                    for name, total in values.items()
                    if name != "_count"
                }
            return finalized

        category_scores = finalize(category_scores)
        category_operational = finalize(category_operational)
        for category, values in finalize(category_judge).items():
            category_scores[category].update(values)

        interval_metrics = list(INTERVAL_METRICS)
        if self.judge is not None:
            interval_metrics.extend(JUDGE_METRICS)
        category_intervals = {
            category: {
                name: bootstrap_interval(
                    _metric_values(
                        [row for row in per_question if row["category"] == category], name
                    )
                ).as_dict()
                for name in interval_metrics
            }
            for category in category_scores
        }
        overall_intervals = {
            name: bootstrap_interval(_metric_values(per_question, name)).as_dict()
            for name in interval_metrics
        }

        router_report = evaluate_router_decisions(router_predictions)
        total = len(per_question)
        cache_hits = sum(row["operational"]["is_cached"] for row in per_question)
        cache_hit_rate = round(cache_hits / total, 4) if total else 0.0
        total_cost = gateway.total_spent_usd
        latencies = [row["operational"]["latency_ms"] for row in per_question]
        p50_latency = percentile(latencies, 0.50)
        p95_latency = percentile(latencies, 0.95)
        # Retrieval-only time: exclude cache hits (no retrieval ran) and never
        # include LLM generation or provider 429 backoff.
        retrieval_latencies = [
            row["operational"]["retrieval_latency_ms"]
            for row in per_question
            if row["operational"]["retrieval_latency_ms"] > 0.0
        ]
        retrieval_p50 = percentile(retrieval_latencies, 0.50) if retrieval_latencies else 0.0
        retrieval_p95 = percentile(retrieval_latencies, 0.95) if retrieval_latencies else 0.0

        judge_model = self.judge.model_name if self.judge is not None else None
        judge_threshold = self.judge.threshold if self.judge is not None else None
        judge_errors = sum(1 for row in per_question if (row.get("judge") or {}).get("error"))

        git_sha: str | None = None
        try:
            git_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
            ).strip()
        except Exception:
            git_sha = None

        return BenchmarkReport(
            total_questions=total,
            overall_router_accuracy=router_report.accuracy,
            split=split or "all",
            retrieval_config=self.retrieval_config,
            git_sha=git_sha,
            category_scores=category_scores,
            category_operational=category_operational,
            per_question=per_question,
            total_cost_usd=total_cost,
            budget_usd=self.budget_usd,
            cache_hit_rate=cache_hit_rate,
            p50_latency_ms=p50_latency,
            p95_latency_ms=p95_latency,
            retrieval_p50_latency_ms=retrieval_p50,
            retrieval_p95_latency_ms=retrieval_p95,
            category_intervals=category_intervals,
            overall_intervals=overall_intervals,
            judge_model=judge_model,
            judge_threshold=judge_threshold,
            summary={
                "git_sha": git_sha,
                "split": split or "all",
                "retrieval_config": self.retrieval_config,
                "router_accuracy": router_report.accuracy,
                "strategy_distribution": router_report.strategy_distribution,
                "category_scores": category_scores,
                "category_operational": category_operational,
                "category_intervals": category_intervals,
                "overall_intervals": overall_intervals,
                "judge_model": judge_model,
                "judge_threshold": judge_threshold,
                "judge_errors": judge_errors,
                "total_cost_usd": total_cost,
                "budget_usd": self.budget_usd,
                "cache_hit_rate": cache_hit_rate,
                "p50_latency_ms": p50_latency,
                "p95_latency_ms": p95_latency,
                "retrieval_p50_latency_ms": retrieval_p50,
                "retrieval_p95_latency_ms": retrieval_p95,
                "gateway_calls": gateway.total_calls,
                "gateway_cache_hits": gateway.cache_hits,
            },
        )


def _judge_metrics(row: dict[str, Any]) -> dict[str, float]:
    """Flatten one row's judge verdict into numeric metrics.

    Rows where the judge failed contribute nothing, so a partial outage does not
    silently drag the mean toward zero; the report carries the error count.
    """
    verdict = row.get("judge")
    if not isinstance(verdict, dict):
        return {}
    metrics: dict[str, float] = {}
    correctness = verdict.get("correctness_score")
    if correctness is not None:
        metrics["judge_correctness"] = float(correctness)
    faithfulness = verdict.get("faithfulness_score")
    if faithfulness is not None:
        metrics["judge_faithfulness"] = float(faithfulness)
    passed = verdict.get("correctness_pass")
    if passed is not None:
        metrics["judge_pass_rate"] = 1.0 if passed else 0.0
    return metrics


def _metric_values(rows: list[dict[str, Any]], name: str) -> list[float]:
    """Return the scored values for one metric across ``rows``."""
    values: list[float] = []
    for row in rows:
        if name in row["chunk_metrics"]:
            values.append(float(row["chunk_metrics"][name]))
        elif name in row["doc_metrics"]:
            values.append(float(row["doc_metrics"][name]))
        elif name in row["answer_metrics"]:
            values.append(float(row["answer_metrics"][name]))
        else:
            value = _judge_metrics(row).get(name)
            if value is not None:
                values.append(value)
    return values
