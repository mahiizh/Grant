from collections import Counter
from dataclasses import dataclass, field


@dataclass
class RouterEvaluationReport:
    """Evaluation metrics for query router accuracy and strategy regret."""

    total_questions: int
    correct_routes: int
    accuracy: float
    confusion_pairs: list[tuple[str, str]] = field(default_factory=list)  # (predicted, expected)
    strategy_distribution: dict[str, int] = field(default_factory=dict)


def evaluate_router_decisions(
    predictions: list[tuple[str, str]],
) -> RouterEvaluationReport:
    """Evaluate router predictions against optimal strategy ground-truth labels.

    predictions: list of (predicted_strategy, expected_strategy).
    """
    total = len(predictions)
    if total == 0:
        return RouterEvaluationReport(
            total_questions=0,
            correct_routes=0,
            accuracy=0.0,
        )

    correct = sum(1 for pred, exp in predictions if pred == exp)
    dist = dict(Counter(pred for pred, _ in predictions))

    return RouterEvaluationReport(
        total_questions=total,
        correct_routes=correct,
        accuracy=round(correct / total, 4),
        confusion_pairs=predictions,
        strategy_distribution=dist,
    )
