"""Deterministic bootstrap confidence intervals for evaluation metrics.

Item 6 makes "A beats B" a claim that needs evidence. Point estimates alone are
not evidence: a 0.02 difference over 30 rows is noise. These helpers resample
the scored rows with a fixed seed and report a percentile interval, plus a
paired interval for the difference between two configurations on the *same*
questions. Intervals are deterministic for a given input and seed, so a report
can be reproduced exactly.

The percentile bootstrap is used instead of a normal approximation because the
metrics are bounded in ``[0, 1]`` and many cells are small or near the boundary.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

DEFAULT_ITERATIONS = 2000
DEFAULT_CONFIDENCE = 0.95
DEFAULT_SEED = 20260412


@dataclass(frozen=True)
class Interval:
    """A point estimate and its bootstrap interval."""

    mean: float
    low: float
    high: float
    n: int

    def as_dict(self) -> dict[str, float | int]:
        return {"mean": self.mean, "low": self.low, "high": self.high, "n": self.n}

    def overlaps(self, other: Interval) -> bool:
        return self.low <= other.high and other.low <= self.high


def _percentile(sorted_values: Sequence[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    position = (len(sorted_values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * weight


def bootstrap_interval(
    values: Iterable[float],
    *,
    iterations: int = DEFAULT_ITERATIONS,
    confidence: float = DEFAULT_CONFIDENCE,
    seed: int = DEFAULT_SEED,
) -> Interval:
    """Return the mean and a percentile bootstrap interval for ``values``.

    An empty input yields a zero interval with ``n=0`` rather than raising, so a
    category with no rows still renders in a report.
    """
    materialized = [float(value) for value in values]
    n = len(materialized)
    if n == 0:
        return Interval(mean=0.0, low=0.0, high=0.0, n=0)
    if n == 1:
        value = round(materialized[0], 4)
        return Interval(mean=value, low=value, high=value, n=1)

    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(max(1, iterations)):
        sample = [materialized[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()

    tail = (1.0 - confidence) / 2.0
    return Interval(
        mean=round(sum(materialized) / n, 4),
        low=round(_percentile(means, tail), 4),
        high=round(_percentile(means, 1.0 - tail), 4),
        n=n,
    )


def paired_bootstrap_difference(
    left: Iterable[float],
    right: Iterable[float],
    *,
    iterations: int = DEFAULT_ITERATIONS,
    confidence: float = DEFAULT_CONFIDENCE,
    seed: int = DEFAULT_SEED,
) -> Interval:
    """Bootstrap the mean of ``left - right`` using paired observations.

    ``left`` and ``right`` must be aligned by question. Pairing removes the
    question-difficulty variance that makes independent intervals overlap even
    when one configuration is consistently better.
    """
    left_values = [float(value) for value in left]
    right_values = [float(value) for value in right]
    if len(left_values) != len(right_values):
        raise ValueError(
            f"Paired samples must be the same length ({len(left_values)} != {len(right_values)})"
        )
    differences = [a - b for a, b in zip(left_values, right_values, strict=True)]
    return bootstrap_interval(
        differences,
        iterations=iterations,
        confidence=confidence,
        seed=seed,
    )
