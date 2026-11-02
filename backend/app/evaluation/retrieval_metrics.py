import math
from collections.abc import Sequence


def recall_at_k(
    retrieved_ids: Sequence[str],
    ground_truth_ids: set[str] | Sequence[str],
    k: int,
) -> float:
    """Calculate Recall@K: proportion of relevant items retrieved in top-K."""
    if k <= 0:
        return 0.0

    targets = set(ground_truth_ids)
    if not targets:
        return 1.0 if len(retrieved_ids[:k]) == 0 else 0.0

    top_k = set(retrieved_ids[:k])
    hits = len(top_k & targets)
    return hits / len(targets)


def precision_at_k(
    retrieved_ids: Sequence[str],
    ground_truth_ids: set[str] | Sequence[str],
    k: int,
) -> float:
    """Calculate Precision@K: proportion of top-K items that are relevant."""
    if k <= 0:
        return 0.0

    targets = set(ground_truth_ids)
    top_k_list = retrieved_ids[:k]
    if not top_k_list:
        return 1.0 if not targets else 0.0

    top_k = set(top_k_list)
    hits = len(top_k & targets)
    return hits / k


def reciprocal_rank(
    retrieved_ids: Sequence[str],
    ground_truth_ids: set[str] | Sequence[str],
) -> float:
    """Calculate Reciprocal Rank (RR): 1 / rank of the first relevant retrieved item."""
    targets = set(ground_truth_ids)
    if not targets:
        return 1.0 if len(retrieved_ids) == 0 else 0.0

    for rank, item_id in enumerate(retrieved_ids, start=1):
        if item_id in targets:
            return 1.0 / rank
    return 0.0


def hit_rate_at_k(
    retrieved_ids: Sequence[str],
    ground_truth_ids: set[str] | Sequence[str],
    k: int,
) -> float:
    """Calculate Hit Rate@K: 1.0 if at least one relevant item is in top-K, else 0.0."""
    if k <= 0:
        return 0.0

    targets = set(ground_truth_ids)
    if not targets:
        return 1.0 if len(retrieved_ids[:k]) == 0 else 0.0

    top_k = set(retrieved_ids[:k])
    return 1.0 if bool(top_k & targets) else 0.0


def ndcg_at_k(
    retrieved_ids: Sequence[str],
    ground_truth_ids: set[str] | Sequence[str],
    k: int = 10,
) -> float:
    """Calculate Normalized Discounted Cumulative Gain (nDCG@K) with binary relevance."""
    if k <= 0:
        return 0.0

    targets = set(ground_truth_ids)
    if not targets:
        return 1.0 if len(retrieved_ids[:k]) == 0 else 0.0

    # Calculate DCG@K
    dcg = 0.0
    for rank, item_id in enumerate(retrieved_ids[:k], start=1):
        if item_id in targets:
            dcg += 1.0 / math.log2(rank + 1)

    # Calculate Ideal DCG (IDCG@K)
    num_relevant_in_top_k = min(k, len(targets))
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, num_relevant_in_top_k + 1))

    if idcg == 0.0:
        return 0.0

    return dcg / idcg


def evaluate_retrieval(
    retrieved_ids: Sequence[str],
    ground_truth_ids: set[str] | Sequence[str],
    k_values: Sequence[int] = (1, 3, 5, 10),
) -> dict[str, float]:
    """Compute standard IR evaluation metrics for a single retrieval query."""
    targets = set(ground_truth_ids)
    results: dict[str, float] = {
        "mrr": reciprocal_rank(retrieved_ids, targets),
    }

    for k in k_values:
        results[f"recall@{k}"] = recall_at_k(retrieved_ids, targets, k)
        results[f"precision@{k}"] = precision_at_k(retrieved_ids, targets, k)
        results[f"ndcg@{k}"] = ndcg_at_k(retrieved_ids, targets, k)
        results[f"hit_rate@{k}"] = hit_rate_at_k(retrieved_ids, targets, k)

    return results
