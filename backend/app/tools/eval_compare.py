"""Run the five retrieval configurations and print one honest comparison table.

This is the item-6b baseline harness. It ingests the corpus once into the
isolated eval stores, then runs ``dense``, ``sparse``, ``hybrid``, ``full`` and
``graph_forced`` against the same golden split, ACL scope, and retrieval stack.
Each configuration gets a cold on-disk LLM cache and exact/semantic response
caching is disabled, so a cache hit cannot return results from another config.
``--retrieval-only`` skips answer generation while retaining multi-turn
query rewrites.
"""

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.evaluation.bootstrap import (
    cluster_paired_bootstrap_difference,
    cluster_paired_bootstrap_sd,
    paired_bootstrap_difference,
    paired_sd,
)
from app.evaluation.calibration import load_agreement
from app.evaluation.datasets import SplitType
from app.evaluation.runner import BenchmarkReport, diff_metrics
from app.orchestration.state import RETRIEVAL_CONFIGS, RetrievalConfig
from app.tools.eval_cli import (
    _print_report,
    configure_llm_cache,
    prepare_eval,
    run_config,
)


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _metric_value(row: dict[str, Any], metric: str) -> float | None:
    if metric in row["chunk_metrics"]:
        return float(row["chunk_metrics"][metric])
    if metric in row["doc_metrics"]:
        return float(row["doc_metrics"][metric])
    if metric in row["answer_metrics"]:
        return float(row["answer_metrics"][metric])
    verdict = row.get("judge") or {}
    if metric == "judge_correctness":
        value = verdict.get("correctness_score")
        return float(value) if value is not None else None
    if metric == "judge_faithfulness":
        value = verdict.get("faithfulness_score")
        return float(value) if value is not None else None
    if metric == "judge_pass_rate":
        value = verdict.get("correctness_pass")
        return (1.0 if value else 0.0) if value is not None else None
    return None


def _overall(report: BenchmarkReport, metric: str) -> float:
    values = [
        value for row in report.per_question if (value := _metric_value(row, metric)) is not None
    ]
    return _mean(values)


def _interval(report: BenchmarkReport, category: str | None, metric: str) -> dict[str, Any]:
    source = (
        report.overall_intervals
        if category is None
        else report.category_intervals.get(category, {})
    )
    interval = source.get(metric)
    if interval:
        return interval
    value = (
        _overall(report, metric)
        if category is None
        else report.category_scores.get(category, {}).get(metric, 0.0)
    )
    return {"mean": value, "low": value, "high": value, "n": 0}


def _format_interval(interval: dict[str, Any]) -> str:
    return (
        f"{float(interval['mean']):.3f}[{float(interval['low']):.2f},{float(interval['high']):.2f}]"
    )


def _cell(report: BenchmarkReport, category: str | None, metrics: tuple[str, ...]) -> str:
    return " / ".join(_format_interval(_interval(report, category, metric)) for metric in metrics)


def _print_comparison(
    reports: dict[RetrievalConfig, BenchmarkReport],
    split: str,
) -> None:
    categories = sorted(
        {row["category"] for report in reports.values() for row in report.per_question}
    )
    agreement = load_agreement()
    judge_enabled = any(report.judge_model for report in reports.values())

    print()
    print("=" * 120)
    print(
        f"Retrieval ablation comparison (split={split}) — cell = point estimate [95% bootstrap CI]"
    )
    if all(report.retrieval_only for report in reports.values()):
        print("Mode: retrieval-only (no answer generation; multi-turn rewrites included)")
    elif any(report.retrieval_only for report in reports.values()):
        print("Mode: MIXED retrieval-only/generative reports — do not compare blindly")
    git_shas = {report.git_sha for report in reports.values() if report.git_sha}
    if git_shas:
        print(f"Git commit(s): {', '.join(sorted(git_shas))}")
    if judge_enabled:
        models = sorted({report.judge_model for report in reports.values() if report.judge_model})
        if agreement is not None:
            print(
                f"Judge: model={', '.join(models)} threshold={agreement.threshold} "
                f"agreement={agreement.raw_agreement:.3f} "
                f"kappa={agreement.cohen_kappa:.3f} (n={agreement.n})"
            )
        else:
            print(
                f"Judge: model={', '.join(models)} — NOT CALIBRATED. "
                "Run `make calibrate-judge` before trusting judge columns."
            )
    print("=" * 120)
    print("Retrieval quality:")
    print("| category | " + " | ".join(RETRIEVAL_CONFIGS) + " |")
    print("|---|" + "|".join("---" for _ in RETRIEVAL_CONFIGS) + "|")
    for category in categories:
        cells = [
            _cell(reports[config], category, ("chunk_recall@5", "chunk_ndcg@10"))
            for config in RETRIEVAL_CONFIGS
        ]
        print(f"| {category} | " + " | ".join(cells) + " |")
    print(
        "| **overall** | "
        + " | ".join(
            _cell(reports[config], None, ("chunk_recall@5", "chunk_ndcg@10"))
            for config in RETRIEVAL_CONFIGS
        )
        + " |"
    )

    print()
    print(
        "Answer quality (answer accuracy is a secondary floor; "
        "token F1 is shown only in the operational block):"
    )
    answer_metrics: tuple[str, ...] = ("answer_accuracy",)
    if judge_enabled:
        answer_metrics = ("answer_accuracy", "judge_correctness", "judge_pass_rate")
    print("| category | " + " | ".join(RETRIEVAL_CONFIGS) + " |")
    print("|---|" + "|".join("---" for _ in RETRIEVAL_CONFIGS) + "|")
    for category in categories:
        answer_cells = [
            _cell(reports[config], category, answer_metrics) for config in RETRIEVAL_CONFIGS
        ]
        print(f"| {category} | " + " | ".join(answer_cells) + " |")
    print(
        "| **overall** | "
        + " | ".join(_cell(reports[config], None, answer_metrics) for config in RETRIEVAL_CONFIGS)
        + " |"
    )

    print()
    print("Router decisions for multi_hop rows (decision is recorded before any config bypass):")
    print("| config | graph | vector | hybrid | abstain | graph_share |")
    print("|---|---:|---:|---:|---:|---:|")
    for config in RETRIEVAL_CONFIGS:
        routes = Counter(
            str(row["route"])
            for row in reports[config].per_question
            if row["category"] == "multi_hop"
        )
        total = sum(routes.values())
        graph_share = routes["graph"] / total if total else 0.0
        print(
            f"| {config} | {routes['graph']} | {routes['vector']} | {routes['hybrid']} "
            f"| {routes['abstain']} | {graph_share:.3f} |"
        )
    full_routes = Counter(
        str(row["route"]) for row in reports["full"].per_question if row["category"] == "multi_hop"
    )
    full_total = sum(full_routes.values())
    full_graph_share = full_routes["graph"] / full_total if full_total else 0.0
    if full_graph_share < 0.5:
        print(
            f"FINDING: full routed only {full_routes['graph']}/{full_total} multi_hop rows "
            "to graph (<50%). Router patterns were left unchanged in Phase A."
        )

    baseline = RETRIEVAL_CONFIGS[0]
    print()
    print(
        f"Paired difference vs {baseline} (config minus {baseline}). "
        "Each cell shows the row-bootstrap CI (n=rows) then the cluster-bootstrap "
        "CI (n_clusters=resampling clusters); both use 95% percentile intervals."
    )
    diff_metric_names = diff_metrics(judge_enabled)
    for metric in diff_metric_names:
        print()
        print(f"**{metric}**")
        print("| category | " + " | ".join(RETRIEVAL_CONFIGS[1:]) + " |")
        print("|---|" + "|".join("---" for _ in RETRIEVAL_CONFIGS[1:]) + "|")
        for category in [*categories, None]:
            cells = [
                _paired_cell(reports, config, baseline, metric, category)
                for config in RETRIEVAL_CONFIGS[1:]
            ]
            label = "**overall**" if category is None else category
            print(f"| {label} | " + " | ".join(cells) + " |")

        print()
        print(f"Observed paired SD of {metric} (rows / cluster-bootstrap):")
        for config in RETRIEVAL_CONFIGS[1:]:
            print(
                f"  {config:12s} "
                f"row_sd={_paired_sd(reports, config, baseline, metric):.4f}  "
                f"cluster_bootstrap_sd={_cluster_sd(reports, config, baseline, metric):.4f}"
            )

    print()
    print("Operational (whole split; retrieval latency excludes LLM and 429 backoff):")
    for config in RETRIEVAL_CONFIGS:
        report = reports[config]
        print(
            f"  {config:7s} retrieval_p50={report.retrieval_p50_latency_ms:7.1f} ms  "
            f"retrieval_p95={report.retrieval_p95_latency_ms:7.1f} ms  "
            f"e2e_p50={report.p50_latency_ms:8.1f} ms  "
            f"e2e_p95={report.p95_latency_ms:8.1f} ms  "
            f"cost=${report.total_cost_usd:.6f}  "
            f"cache_hit={report.cache_hit_rate:.3f}  "
            f"answer_f1={_overall(report, 'answer_f1'):.3f}"
        )
    print("=" * 120)


def _values_by_id(report: BenchmarkReport, metric: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for row in report.per_question:
        value = _metric_value(row, metric)
        if value is not None:
            values[str(row["id"])] = value
    return values


def _clusters_by_id(report: BenchmarkReport) -> dict[str, str]:
    return {
        str(row["id"]): str(row.get("cluster_id") or f"hand_{row['id']}")
        for row in report.per_question
    }


def _aligned_pair(
    reports: dict[RetrievalConfig, BenchmarkReport],
    config: RetrievalConfig,
    baseline: RetrievalConfig,
    metric: str,
    category: str | None,
) -> tuple[list[float], list[float], list[str]]:
    left = _values_by_id(reports[config], metric)
    right = _values_by_id(reports[baseline], metric)
    clusters = _clusters_by_id(reports[baseline])
    categories_by_id = {str(row["id"]): row["category"] for row in reports[config].per_question}
    shared = [
        question_id
        for question_id in sorted(set(left) & set(right))
        if category is None or categories_by_id.get(question_id) == category
    ]
    return (
        [left[question_id] for question_id in shared],
        [right[question_id] for question_id in shared],
        [clusters.get(question_id, f"hand_{question_id}") for question_id in shared],
    )


def _paired_cell(
    reports: dict[RetrievalConfig, BenchmarkReport],
    config: RetrievalConfig,
    baseline: RetrievalConfig,
    metric: str,
    category: str | None,
) -> str:
    left, right, clusters = _aligned_pair(reports, config, baseline, metric, category)
    row_interval = paired_bootstrap_difference(left, right)
    cluster_interval = cluster_paired_bootstrap_difference(left, right, clusters)
    return (
        f"{row_interval.mean:+.3f} row[{row_interval.low:+.2f},{row_interval.high:+.2f}] "
        f"n={row_interval.n}; cluster[{cluster_interval.low:+.2f},{cluster_interval.high:+.2f}] "
        f"n_clusters={cluster_interval.n}"
    )


def _paired_sd(
    reports: dict[RetrievalConfig, BenchmarkReport],
    config: RetrievalConfig,
    baseline: RetrievalConfig,
    metric: str,
) -> float:
    left, right, _ = _aligned_pair(reports, config, baseline, metric, None)
    return paired_sd(left, right)


def _cluster_sd(
    reports: dict[RetrievalConfig, BenchmarkReport],
    config: RetrievalConfig,
    baseline: RetrievalConfig,
    metric: str,
) -> float:
    left, right, clusters = _aligned_pair(reports, config, baseline, metric, None)
    return cluster_paired_bootstrap_sd(left, right, clusters)


def _write_reports(
    reports: dict[RetrievalConfig, BenchmarkReport],
    json_dir: Path,
) -> None:
    json_dir.mkdir(parents=True, exist_ok=True)
    for config, report in reports.items():
        payload: dict[str, Any] = {
            "retrieval_config": report.retrieval_config,
            "retrieval_only": report.retrieval_only,
            "split": report.split,
            "total_questions": report.total_questions,
            "category_scores": report.category_scores,
            "category_operational": report.category_operational,
            "total_cost_usd": report.total_cost_usd,
            "cache_hit_rate": report.cache_hit_rate,
            "p50_latency_ms": report.p50_latency_ms,
            "p95_latency_ms": report.p95_latency_ms,
            "retrieval_p50_latency_ms": report.retrieval_p50_latency_ms,
            "retrieval_p95_latency_ms": report.retrieval_p95_latency_ms,
            "category_intervals": report.category_intervals,
            "overall_intervals": report.overall_intervals,
            "judge_model": report.judge_model,
            "judge_threshold": report.judge_threshold,
            "summary": report.summary,
            "per_question": report.per_question,
        }
        (json_dir / f"eval-{config}.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
    print(f"Wrote per-config JSON reports to {json_dir}")


async def _run(args: argparse.Namespace) -> int:
    dataset = await prepare_eval()
    split: SplitType | None = None if args.split == "all" else args.split

    reports: dict[RetrievalConfig, BenchmarkReport] = {}
    for config in RETRIEVAL_CONFIGS:
        cache_dir = configure_llm_cache(config, fresh=True)
        print()
        print(f"### config={config} (cold LLM cache: {cache_dir})")
        report = await run_config(
            dataset=dataset,
            config=config,
            split=split,
            budget_usd=args.budget_usd,
            concurrency=args.concurrency,
            cache_enabled=False,
            retrieval_only=args.retrieval_only,
            judge_enabled=args.judge,
            judge_model=args.judge_model,
            judge_threshold=args.judge_threshold,
        )
        reports[config] = report
        _print_report(report)

    _print_comparison(reports, args.split)

    if args.json_dir:
        _write_reports(reports, Path(args.json_dir))

    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare dense, sparse, hybrid, full, and graph_forced retrieval configurations."
    )
    parser.add_argument(
        "--split",
        choices=["dev", "test", "all"],
        default="test",
        help="Golden split to score (default: test).",
    )
    parser.add_argument(
        "--budget-usd",
        type=float,
        default=None,
        help="Per-config LLM budget cap. Defaults to LLM_MAX_BUDGET_PER_RUN.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="Max concurrent questions per config. Defaults to EVAL_CONCURRENCY.",
    )
    parser.add_argument(
        "--json-dir",
        default=None,
        help="Optional directory for one JSON report per configuration.",
    )
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Skip answer generation; multi-turn query rewrites still run.",
    )
    parser.add_argument(
        "--judge",
        action="store_true",
        help="Score answers with the DeepEval LLM judge (uses provider quota).",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="Judge model. Defaults to EVAL_JUDGE_MODEL or LLM_MODEL.",
    )
    parser.add_argument(
        "--judge-threshold",
        type=float,
        default=None,
        help="Judge pass threshold. Defaults to EVAL_JUDGE_THRESHOLD (0.5).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
