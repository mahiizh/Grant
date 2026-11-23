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
import statistics
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


def paired_sd(left: Iterable[float], right: Iterable[float]) -> float:
    """Return the sample standard deviation of aligned paired differences."""
    left_values = [float(value) for value in left]
    right_values = [float(value) for value in right]
    if len(left_values) != len(right_values):
        raise ValueError(
            f"Paired samples must be the same length ({len(left_values)} != {len(right_values)})"
        )
    differences = [a - b for a, b in zip(left_values, right_values, strict=True)]
    if len(differences) < 2:
        return 0.0
    return round(statistics.stdev(differences), 4)


def _cluster_groups(
    values: Sequence[float],
    cluster_ids: Sequence[str],
) -> tuple[dict[str, list[float]], list[str]]:
    if len(values) != len(cluster_ids):
        raise ValueError(
            f"Values and clusters must be the same length ({len(values)} != {len(cluster_ids)})"
        )
    groups: dict[str, list[float]] = {}
    order: list[str] = []
    for value, cluster_id in zip(values, cluster_ids, strict=True):
        if cluster_id not in groups:
            groups[cluster_id] = []
            order.append(cluster_id)
        groups[cluster_id].append(value)
    return groups, order


def _cluster_replicates(
    values: Sequence[float],
    cluster_ids: Sequence[str],
    *,
    iterations: int,
    seed: int,
) -> list[list[float]]:
    groups, order = _cluster_groups(values, cluster_ids)
    if not order:
        return []
    rng = random.Random(seed)
    replicates: list[list[float]] = []
    for _ in range(max(1, iterations)):
        sampled_clusters = [order[rng.randrange(len(order))] for _ in order]
        replicates.append([value for cluster in sampled_clusters for value in groups[cluster]])
    return replicates


def cluster_bootstrap_interval(
    values: Iterable[float],
    cluster_ids: Sequence[str],
    *,
    iterations: int = DEFAULT_ITERATIONS,
    confidence: float = DEFAULT_CONFIDENCE,
    seed: int = DEFAULT_SEED,
) -> Interval:
    """Bootstrap a mean by resampling whole clusters.

    ``n`` is the effective sample size: the number of clusters, not rows. A
    cluster may contain several correlated rows (one template family or source
    document); resampling rows independently would understate the variance.
    """
    materialized = [float(value) for value in values]
    groups, order = _cluster_groups(materialized, cluster_ids)
    effective_n = len(order)
    if effective_n == 0:
        return Interval(mean=0.0, low=0.0, high=0.0, n=0)
    if effective_n == 1:
        value = round(sum(materialized) / len(materialized), 4)
        return Interval(mean=value, low=value, high=value, n=1)

    means = [
        sum(replicate) / len(replicate)
        for replicate in _cluster_replicates(
            materialized,
            cluster_ids,
            iterations=iterations,
            seed=seed,
        )
    ]
    means.sort()
    tail = (1.0 - confidence) / 2.0
    return Interval(
        mean=round(sum(materialized) / len(materialized), 4),
        low=round(_percentile(means, tail), 4),
        high=round(_percentile(means, 1.0 - tail), 4),
        n=effective_n,
    )


def cluster_paired_bootstrap_difference(
    left: Iterable[float],
    right: Iterable[float],
    cluster_ids: Sequence[str],
    *,
    iterations: int = DEFAULT_ITERATIONS,
    confidence: float = DEFAULT_CONFIDENCE,
    seed: int = DEFAULT_SEED,
) -> Interval:
    """Paired ``left - right`` interval with whole-cluster resampling."""
    left_values = [float(value) for value in left]
    right_values = [float(value) for value in right]
    if len(left_values) != len(right_values):
        raise ValueError(
            f"Paired samples must be the same length ({len(left_values)} != {len(right_values)})"
        )
    differences = [a - b for a, b in zip(left_values, right_values, strict=True)]
    return cluster_bootstrap_interval(
        differences,
        cluster_ids,
        iterations=iterations,
        confidence=confidence,
        seed=seed,
    )


def cluster_paired_bootstrap_sd(
    left: Iterable[float],
    right: Iterable[float],
    cluster_ids: Sequence[str],
    *,
    iterations: int = DEFAULT_ITERATIONS,
    seed: int = DEFAULT_SEED,
) -> float:
    """Cluster-bootstrap estimate of the SD of paired differences.

    Each replicate resamples whole clusters, then measures the spread of its
    paired differences. Averaging those spreads keeps the result on the
    observation scale required by the preregistered power formula, while
    accounting for within-cluster correlation.
    """
    left_values = [float(value) for value in left]
    right_values = [float(value) for value in right]
    if len(left_values) != len(right_values):
        raise ValueError(
            f"Paired samples must be the same length ({len(left_values)} != {len(right_values)})"
        )
    differences = [a - b for a, b in zip(left_values, right_values, strict=True)]
    replicates = _cluster_replicates(differences, cluster_ids, iterations=iterations, seed=seed)
    spreads = [
        statistics.stdev(replicate) if len(replicate) >= 2 else 0.0 for replicate in replicates
    ]
    if not spreads:
        return 0.0
    return round(sum(spreads) / len(spreads), 4)
