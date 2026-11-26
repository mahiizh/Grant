"""Derive the four answer-metadata fields persisted with every answer.

The values are computed from the final workflow state so every terminal path
(docs, web, model, abstain, small talk and exact-cache hit) stores the same
shape of metadata. ``path`` describes the answer-source hops, e.g.
``["docs", "web"]`` rendered as ``docs→web``; it is distinct from the graph
traversal path stored in ``RAGState["path"]``.
"""

from __future__ import annotations

from typing import Any, Mapping

AnswerSource = str


def build_answer_metadata(
    state: Mapping[str, Any],
    *,
    stage_timings_ms: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Return source, path, top_score and stage timings for a finished answer."""
    route = str(state.get("route") or "")
    source_kind = str(state.get("source_kind") or "docs")
    is_abstention = bool(state.get("is_abstention", False))

    if is_abstention or route == "abstain":
        source: AnswerSource = "abstain"
    elif route == "small_talk" or source_kind == "unverified":
        source = "model"
    elif source_kind == "web":
        source = "web"
    else:
        source = "docs"

    if source == "abstain":
        answer_path = ["docs", "abstain"] if route != "abstain" else ["abstain"]
    elif source == "model":
        answer_path = ["model"] if route == "small_talk" else ["docs", "web", "model"]
    elif source == "web":
        answer_path = ["web"] if state.get("force_web") else ["docs", "web"]
    else:
        answer_path = ["docs"]

    evidence = list(state.get("evidence") or [])
    scores = [float(getattr(ev, "score", 0.0) or 0.0) for ev in evidence]
    top_score = round(max(scores), 5) if scores else 0.0

    timings = (
        dict(stage_timings_ms)
        if stage_timings_ms is not None
        else dict(state.get("stage_timings_ms") or {})
    )

    return {
        "source": source,
        "answer_path": answer_path,
        "top_score": top_score,
        "stage_timings_ms": timings,
    }
