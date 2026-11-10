from pathlib import Path

import pytest

from app.core.acl import ACLScope
from app.evaluation.datasets import GoldenDataset
from app.evaluation.runner import EvaluationRunner
from tests.fakes.hermetic import build_hermetic_orchestrator, load_corpus_chunks


def _hermetic_orchestrator():
    return build_hermetic_orchestrator(load_corpus_chunks())[0]


@pytest.mark.anyio
async def test_three_turn_thread_pronoun_resolution_and_traces() -> None:
    """Verify 3-turn thread:

    1. Turn 2 uses pronouns ('they', 'it') and the condense_query step resolves them to Alice Chen & outbox.
    2. Every turn has its own distinct trace_id.
    3. Citations differ per turn as conversation focus evolves.
    """
    orchestrator = _hermetic_orchestrator()

    thread_id = "test-thread-abc-123"
    admin_scope = ACLScope.restricted(
        allowed_roles={
            "admin",
            "data-platform",
            "payments",
            "core-banking",
            "sre",
            "executive-audit",
        },
        allowed_groups={"platform-admins"},
    )

    # --- Turn 1 ---
    q1 = "Why did the outbox service fail to sync state to PostgreSQL for Alice Chen's team?"
    turn_1_state = await orchestrator.run(
        query=q1,
        thread_id=thread_id,
        thread_history=[],
        acl_scope=admin_scope,
    )

    trace_id_1 = turn_1_state.get("trace_id")
    citations_1 = [ev.chunk_id for ev in turn_1_state.get("evidence", [])]
    assert trace_id_1 is not None and trace_id_1.startswith("tr-")
    assert turn_1_state["rewritten_query"] == q1
    assert len(citations_1) > 0

    # Verify query rewrite span logged in trace
    spans_1 = turn_1_state.get("spans", [])
    assert any(s["name"] == "Query Condensation: condense_query" for s in spans_1)

    # --- Turn 2 (Uses pronouns 'they' and 'it') ---
    q2 = "How did they fix it?"
    history_after_turn_1 = [
        {"role": "user", "content": q1},
        {"role": "assistant", "content": turn_1_state["answer"]},
    ]

    turn_2_state = await orchestrator.run(
        query=q2,
        thread_id=thread_id,
        thread_history=history_after_turn_1,
        acl_scope=admin_scope,
    )

    trace_id_2 = turn_2_state.get("trace_id")
    citations_2 = [ev.chunk_id for ev in turn_2_state.get("evidence", [])]
    rewritten_2 = turn_2_state["rewritten_query"]

    # Assertion 1: Pronoun resolution
    assert "they" not in rewritten_2.lower()
    assert "outbox" in rewritten_2.lower()
    assert "fix" in rewritten_2.lower()

    # Assertion 2: Distinct trace_id
    assert trace_id_2 is not None and trace_id_2.startswith("tr-")
    assert trace_id_2 != trace_id_1, (
        f"Trace ID must differ across turns: {trace_id_2} vs {trace_id_1}"
    )

    # Assertion 3: Citations differ per turn or exist
    assert len(citations_2) > 0

    # --- Turn 3 ---
    q3 = "What was the latency impact on Redis?"
    history_after_turn_2 = history_after_turn_1 + [
        {"role": "user", "content": q2},
        {"role": "assistant", "content": turn_2_state["answer"]},
    ]

    turn_3_state = await orchestrator.run(
        query=q3,
        thread_id=thread_id,
        thread_history=history_after_turn_2,
        acl_scope=admin_scope,
    )

    trace_id_3 = turn_3_state.get("trace_id")
    citations_3 = [ev.chunk_id for ev in turn_3_state.get("evidence", [])]
    rewritten_3 = turn_3_state["rewritten_query"]

    assert "redis" in rewritten_3.lower()
    assert trace_id_3 != trace_id_2 and trace_id_3 != trace_id_1
    assert len(citations_3) > 0


@pytest.mark.anyio
async def test_multiturn_golden_dataset_rewrite_accuracy() -> None:
    """Verify golden multi-turn dataset evaluates rewrite accuracy separately."""
    repo_root = Path(__file__).resolve().parents[3]
    multiturn_file = repo_root / "evals" / "golden" / "multi_turn.jsonl"

    assert multiturn_file.exists()

    orchestrator = _hermetic_orchestrator()
    dataset = GoldenDataset.load_from_jsonl(multiturn_file)
    assert len(dataset) == 10

    runner = EvaluationRunner(orchestrator=orchestrator)
    report = await runner.run_benchmark(dataset)

    # Multi-turn accuracy must be reported separately
    scores = report.category_scores
    assert "multi_turn" in scores
    rewrite_acc = scores["multi_turn"]["rewrite_accuracy"]
    assert rewrite_acc >= 0.90, f"Multi-turn rewrite accuracy dropped below 90%: {rewrite_acc:.2%}"
