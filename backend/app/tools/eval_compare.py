"""Run the four retrieval configurations and print one honest comparison table.

This is the item-4 baseline harness. It ingests the corpus once into the
isolated eval stores, then runs ``dense``, ``sparse``, ``hybrid`` and ``full``
against the same golden split, prompt, model, and ACL scope. Each configuration
gets a cold on-disk LLM cache and exact/semantic response caching is disabled
for the whole run, so a cache hit cannot return an answer produced by another
configuration.
"""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.evaluation.bootstrap import paired_bootstrap_difference
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

    baseline = RETRIEVAL_CONFIGS[0]
    print()
    print(
        f"Paired difference vs {baseline} (config minus {baseline}; "
        "an interval that excludes 0 is evidence of a real difference):"
    )
    diff_metric_names = diff_metrics(judge_enabled)
    print("| config | " + " | ".join(diff_metric_names) + " |")
    print("|---|" + "|".join("---" for _ in diff_metric_names) + "|")
    baseline_values = {
        metric: _values_by_id(reports[baseline], metric) for metric in diff_metric_names
    }
    for config in RETRIEVAL_CONFIGS[1:]:
        diff_cells: list[str] = []
        for metric in diff_metric_names:
            values = _values_by_id(reports[config], metric)
            shared = sorted(set(values) & set(baseline_values[metric]))
            interval = paired_bootstrap_difference(
                [values[question_id] for question_id in shared],
                [baseline_values[metric][question_id] for question_id in shared],
            )
            diff_cells.append(
                f"{interval.mean:+.3f}[{interval.low:+.2f},{interval.high:+.2f}] (n={interval.n})"
            )
        print(f"| {config} | " + " | ".join(diff_cells) + " |")

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


def _write_reports(
    reports: dict[RetrievalConfig, BenchmarkReport],
    json_dir: Path,
) -> None:
    json_dir.mkdir(parents=True, exist_ok=True)
    for config, report in reports.items():
        payload: dict[str, Any] = {
            "retrieval_config": report.retrieval_config,
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
        description="Compare dense, sparse, hybrid, and full retrieval configurations."
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
