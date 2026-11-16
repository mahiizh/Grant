"""Calibrate the LLM judge against 30 hand-labelled answers.

The calibration set is ``evals/calibration/judge_answers.jsonl``: question,
candidate answer, reference answer, and a binary human label. This tool runs the
same judge used by the benchmark, compares its pass/fail labels with the human
labels, and reports raw agreement plus Cohen's kappa.

``--write`` updates ``evals/calibration/judge_agreement.json``. Comparison
reports read that file; without it they print "NOT CALIBRATED" instead of
pretending the judge is trustworthy.

Calibration is deliberately *not* run on the test split: it is a property of the
judge, not of retrieval, and test is reserved for the final gate.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from app.evaluation.calibration import (
    DEFAULT_AGREEMENT_PATH,
    DEFAULT_ANSWERS_PATH,
    REPO_ROOT,
    cohen_kappa,
)
from app.evaluation.judge import AnswerJudge
from app.llm.gateway import ModelGateway


def _display_path(path: Path) -> str:
    """Return a repo-relative path so the committed artifact is portable."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _load_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    answers_path = Path(args.answers) if args.answers else DEFAULT_ANSWERS_PATH
    agreement_path = Path(args.output) if args.output else DEFAULT_AGREEMENT_PATH
    rows = _load_rows(answers_path)
    if len(rows) != 30:
        print(f"Calibration set has {len(rows)} rows; the approved design requires 30.")
        return 1

    model_name = args.judge_model or settings.EVAL_JUDGE_MODEL or settings.LLM_MODEL
    threshold = (
        args.judge_threshold
        if args.judge_threshold is not None
        else settings.EVAL_JUDGE_THRESHOLD
    )
    gateway = ModelGateway(
        default_model=model_name,
        max_budget_per_run=args.budget_usd or settings.LLM_MAX_BUDGET_PER_RUN,
    )
    judge = AnswerJudge(gateway=gateway, model_name=model_name, threshold=threshold)
    print(f"Calibrating judge model={model_name} threshold={threshold} on {len(rows)} rows.")

    human: list[int] = []
    predicted: list[int] = []
    per_row: list[dict[str, object]] = []
    for row in rows:
        verdict = await judge.evaluate(
            question=str(row["question"]),
            answer=str(row["answer"]),
            expected_answer=str(row["reference"]),
            context=None,
        )
        if verdict.correctness_pass is None:
            print(f"  {row['id']}: judge error: {verdict.error}")
            per_row.append(
                {
                    "id": row["id"],
                    "human_label": int(str(row["human_label"])),
                    "judge_label": None,
                    "score": None,
                    "reason": verdict.correctness_reason,
                    "error": verdict.error,
                }
            )
            continue
        judge_label = 1 if verdict.correctness_pass else 0
        human.append(int(str(row["human_label"])))
        predicted.append(judge_label)
        per_row.append(
            {
                "id": row["id"],
                "human_label": int(str(row["human_label"])),
                "judge_label": judge_label,
                "score": verdict.correctness_score,
                "reason": verdict.correctness_reason,
                "error": None,
            }
        )

    if not human:
        print("No judge labels produced; nothing to calibrate.")
        return 1
    if len(human) < len(rows) and not args.allow_partial:
        print(f"Only {len(human)}/{len(rows)} rows judged; rerun with --allow-partial to record this.")
        return 1

    raw_agreement = round(sum(1 for a, b in zip(human, predicted, strict=True) if a == b) / len(human), 4)
    kappa = round(cohen_kappa(human, predicted), 4)
    agreement = {
        "model": model_name,
        "raw_agreement": raw_agreement,
        "cohen_kappa": kappa,
        "n": len(human),
        "threshold": threshold,
        "generated_at": datetime.now(UTC).isoformat(),
        "answers_path": _display_path(answers_path),
        "rows": per_row,
    }

    print(f"Raw agreement: {raw_agreement:.4f} ({len(human)} labelled rows)")
    print(f"Cohen's kappa: {kappa:.4f}")
    if args.write:
        agreement_path.parent.mkdir(parents=True, exist_ok=True)
        agreement_path.write_text(json.dumps(agreement, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {agreement_path}")
    else:
        print("Dry run: pass --write to update the committed agreement file.")
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answers", default=None, help="Calibration JSONL path.")
    parser.add_argument("--output", default=None, help="Agreement JSON output path.")
    parser.add_argument("--judge-model", default=None, help="Judge model override.")
    parser.add_argument("--judge-threshold", type=float, default=None, help="Pass threshold.")
    parser.add_argument("--budget-usd", type=float, default=None, help="LLM budget cap.")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Write an agreement file even when some judge calls failed.",
    )
    parser.add_argument("--write", action="store_true", help="Write the agreement file.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
