"""Answer-level scoring for the golden evaluation.

Retrieval metrics only say whether the right chunk was retrieved. They do not
say whether the generated answer is correct. These helpers add a deterministic,
model-free answer score so the four retrieval configurations can be compared on
answer quality as well as retrieval quality.

The metric is SQuAD-style normalized token F1. It is intentionally lexical:
no judge model, no extra API calls, and the same answer text always scores the
same. It is a floor, not a substitute for human review.
"""

import re
import string
from collections import Counter

_ARTICLES = re.compile(r"\b(a|an|the)\b", re.IGNORECASE)
_PUNCTUATION = str.maketrans("", "", string.punctuation)
_WHITESPACE = re.compile(r"\s+")

# An answer counts as correct when it overlaps the reference at least this much.
DEFAULT_ACCURACY_THRESHOLD = 0.5


def normalize_answer(text: str) -> str:
    """Lowercase, strip punctuation/articles, and collapse whitespace."""
    lowered = text.lower().translate(_PUNCTUATION)
    without_articles = _ARTICLES.sub(" ", lowered)
    return _WHITESPACE.sub(" ", without_articles).strip()


def token_f1(prediction: str, reference: str) -> float:
    """Return normalized token-level F1 between a prediction and a reference."""
    pred_tokens = normalize_answer(prediction).split()
    ref_tokens = normalize_answer(reference).split()
    if not pred_tokens or not ref_tokens:
        return 0.0

    common = Counter(pred_tokens) & Counter(ref_tokens)
    num_same = sum(common.values())
    if num_same == 0:
        return 0.0

    precision = num_same / len(pred_tokens)
    recall = num_same / len(ref_tokens)
    return round(2.0 * precision * recall / (precision + recall), 4)


def answer_accuracy(
    prediction: str,
    reference: str | None,
    is_abstention: bool,
    threshold: float = DEFAULT_ACCURACY_THRESHOLD,
) -> tuple[float, float]:
    """Score one answer and return ``(answer_f1, answer_accuracy)``.

    ``reference is None`` marks an unanswerable question: it is correct only
    when the pipeline abstained, and its F1 is reported as 1.0 on a correct
    abstention so the average F1 is not dragged down by an undefined reference.
    """
    if reference is None:
        correct = 1.0 if is_abstention else 0.0
        return correct, correct

    f1 = token_f1(prediction, reference)
    return f1, 1.0 if f1 >= threshold else 0.0
