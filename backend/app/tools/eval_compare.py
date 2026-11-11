"""Run the four retrieval configurations and print one honest comparison table.

This is the item-4 baseline harness. It ingests the corpus once into the
isolated eval stores, then runs ``dense``, ``sparse``, ``hybrid`` and ``full``
against the same golden split, prompt, model, and ACL scope. Each configuration
gets a cold on-disk LLM cache and freshly cleared exact/semantic caches so the
comparison does not inherit a warm run from another configuration.
"""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.evaluation.datasets import SplitType
from app.evaluation.runner import BenchmarkReport
from app.orchestration.state import RETRIEVAL_CONFIGS, RetrievalConfig
from app.tools.eval_cli import (
    _print_report,
    configure_llm_cache,
    prepare_eval,
    run_config,
)


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _overall(report: BenchmarkReport, metric: str) -> float:
    if metric == "answer_accuracy":
        return _mean([row["answer_metrics"]["answer_accuracy"] for row in report.per_question])
    if metric == "answer_f1":
        return _mean([row["answer_metrics"]["answer_f1"] for row in report.per_question])
    return _mean([row["chunk_metrics"][metric] for row in report.per_question])


def _category(report: BenchmarkReport, category: str) -> tuple[float, float, float]:
    scores = report.category_scores.get(category, {})
    return (
        scores.get("chunk_recall@5", 0.0),
        scores.get("chunk_ndcg@10", 0.0),
        scores.get("answer_accuracy", 0.0),
    )


def _cell(values: tuple[float, float, float]) -> str:
    recall, ndcg, accuracy = values
    return f"{recall:.3f} / {ndcg:.3f} / {accuracy:.3f}"


def _print_comparison(
    reports: dict[RetrievalConfig, BenchmarkReport],
    split: str,
) -> None:
    categories = sorted(
        {row["category"] for report in reports.values() for row in report.per_question}
    )
    header = "| category | " + " | ".join(RETRIEVAL_CONFIGS) + " |"
    divider = "|---|" + "|".join("---" for _ in RETRIEVAL_CONFIGS) + "|"

    print()
    print("=" * 96)
    print(
        f"Retrieval ablation comparison (split={split}) — cell = recall@5 / nDCG@10 / answer accuracy"
    )
    print("=" * 96)
    print(header)
    print(divider)
    for category in categories:
        cells = [_cell(_category(reports[config], category)) for config in RETRIEVAL_CONFIGS]
        print(f"| {category} | " + " | ".join(cells) + " |")
    overall = [
        _cell(
            (
                _overall(reports[config], "chunk_recall@5"),
                _overall(reports[config], "chunk_ndcg@10"),
                _overall(reports[config], "answer_accuracy"),
            )
        )
        for config in RETRIEVAL_CONFIGS
    ]
    print("| **overall** | " + " | ".join(overall) + " |")
    print()
    print("Operational (whole split):")
    for config in RETRIEVAL_CONFIGS:
        report = reports[config]
        print(
            f"  {config:7s} p50={report.p50_latency_ms:8.1f} ms  "
            f"p95={report.p95_latency_ms:8.1f} ms  "
            f"cost=${report.total_cost_usd:.6f}  "
            f"cache_hit={report.cache_hit_rate:.3f}  "
            f"answer_f1={_overall(report, 'answer_f1'):.3f}"
        )
    print("=" * 96)


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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
