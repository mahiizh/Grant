"""Unit tests for entity-grounding abstention."""

import pytest

from app.orchestration.grounding import (
    asks_about_absent_entity,
    evidence_mentions_any,
    named_entities,
)
from tests.fakes.hermetic import build_hermetic_orchestrator, load_corpus_chunks


def test_named_entities_ignores_plain_words_and_acronyms() -> None:
    text = "Which team owns PhotonIndex? Did INC-2026-04 impact PostgreSQL?"
    entities = named_entities(text)
    assert "PhotonIndex" in entities
    assert "PostgreSQL" in entities
    # Sentence-initial words and all-caps incident ids are not names.
    assert "Which" not in entities
    assert "INC" not in entities


def test_absent_entity_requires_every_named_entity_to_be_missing() -> None:
    evidence = ["EventStream targets a p99 latency of 33ms."]
    assert asks_about_absent_entity("Which team owns PhotonIndex?", evidence)
    assert not asks_about_absent_entity("What is the p99 latency SLA for EventStream?", evidence)
    # Multi-hop questions stay answerable when part of the chain was retrieved.
    assert not asks_about_absent_entity("How does EventStream depend on PhotonIndex?", evidence)
    # No CamelCase entity means this check does not apply.
    assert not asks_about_absent_entity("What is the p99 latency SLA?", evidence)
    assert evidence_mentions_any(["eventstream"], evidence)


@pytest.mark.anyio
async def test_orchestrator_abstains_on_absent_service() -> None:
    orchestrator, _ = build_hermetic_orchestrator(load_corpus_chunks())
    orchestrator.exact_cache.clear()
    orchestrator.semantic_cache.clear()

    state = await orchestrator.run(query="Which team owns PhotonIndex?")

    assert state["is_abstention"]
    assert "sufficient information" in state["answer"]
    assert state["citations_valid"]
