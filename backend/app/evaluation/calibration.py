"""Judge calibration artifacts and agreement statistics.

A judge is only evidence if its labels agree with a human's. The calibration
run scores 30 hand-labelled answers and writes ``judge_agreement.json`` next to
the labels. Comparison reports read that file and print the agreement figure
beside the judge columns, so a reader can see how much to trust them.

Cohen's kappa is reported alongside raw agreement because raw agreement is
inflated when most answers are easy: a judge that always says "correct" gets
high agreement on a mostly-correct set and a kappa near zero.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CALIBRATION_DIR = REPO_ROOT / "evals" / "calibration"
DEFAULT_ANSWERS_PATH = DEFAULT_CALIBRATION_DIR / "judge_answers.jsonl"
DEFAULT_AGREEMENT_PATH = DEFAULT_CALIBRATION_DIR / "judge_agreement.json"


@dataclass(frozen=True)
class JudgeAgreement:
    """Agreement between judge labels and hand labels."""

    model: str
    raw_agreement: float
    cohen_kappa: float
    n: int
    threshold: float
    generated_at: str

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            "model": self.model,
            "raw_agreement": self.raw_agreement,
            "cohen_kappa": self.cohen_kappa,
            "n": self.n,
            "threshold": self.threshold,
            "generated_at": self.generated_at,
        }


def cohen_kappa(human: list[int], judge: list[int]) -> float:
    """Return Cohen's kappa for two aligned binary label sequences."""
    if len(human) != len(judge):
        raise ValueError(f"Label sequences must align ({len(human)} != {len(judge)})")
    n = len(human)
    if n == 0:
        return 0.0
    observed = sum(1 for a, b in zip(human, judge, strict=True) if a == b) / n
    human_pos = sum(human) / n
    judge_pos = sum(judge) / n
    expected = human_pos * judge_pos + (1 - human_pos) * (1 - judge_pos)
    if expected >= 1.0:
        # Perfectly unanimous marginals: kappa is undefined. Return 1.0 when the
        # raters also agreed on every row, 0.0 otherwise.
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1 - expected)


def load_agreement(path: Path | str | None = None) -> JudgeAgreement | None:
    """Load the committed calibration result, or ``None`` when uncalibrated."""
    target = Path(path) if path is not None else DEFAULT_AGREEMENT_PATH
    if not target.exists():
        return None
    payload = json.loads(target.read_text(encoding="utf-8"))
    return JudgeAgreement(
        model=str(payload["model"]),
        raw_agreement=float(payload["raw_agreement"]),
        cohen_kappa=float(payload["cohen_kappa"]),
        n=int(payload["n"]),
        threshold=float(payload["threshold"]),
        generated_at=str(payload["generated_at"]),
    )
