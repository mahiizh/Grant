from app.evaluation.answer_metrics import answer_accuracy, normalize_answer, token_f1
from app.evaluation.runner import percentile


def test_normalize_answer_strips_case_punctuation_and_articles() -> None:
    assert normalize_answer("The  PostgreSQL, 16!") == "postgresql 16"
    assert normalize_answer("A an the") == ""


def test_token_f1_exact_and_partial_overlap() -> None:
    assert token_f1("PostgreSQL is the source of truth", "PostgreSQL is the source of truth") == 1.0
    assert token_f1("PostgreSQL", "PostgreSQL is the source of truth") < 1.0
    assert token_f1("completely unrelated", "PostgreSQL is the source of truth") == 0.0
    assert token_f1("", "PostgreSQL") == 0.0


def test_answer_accuracy_threshold_and_abstention() -> None:
    f1, correct = answer_accuracy(
        "PostgreSQL is the source of truth",
        "PostgreSQL is the single source of truth",
        is_abstention=False,
    )
    assert f1 > 0.5
    assert correct == 1.0

    f1, correct = answer_accuracy(
        "completely unrelated",
        "PostgreSQL is the source of truth",
        is_abstention=False,
    )
    assert f1 == 0.0
    assert correct == 0.0

    # Unanswerable rows have no reference: only an abstention is correct.
    assert answer_accuracy("anything", None, is_abstention=True) == (1.0, 1.0)
    assert answer_accuracy("anything", None, is_abstention=False) == (0.0, 0.0)


def test_percentile_interpolates() -> None:
    values = [10.0, 20.0, 30.0, 40.0]
    assert percentile(values, 0.5) == 25.0
    assert percentile(values, 0.0) == 10.0
    assert percentile(values, 1.0) == 40.0
    assert percentile([], 0.95) == 0.0
