"""Unit tests for entity-grounding abstention."""

from datetime import UTC, datetime

import pytest

from app.core.acl import ACLScope
from app.domain import Chunk, Provenance
from app.orchestration.grounding import (
    asks_about_absent_entity,
    evidence_mentions_any,
    named_entities,
)
from tests.fakes.hermetic import build_hermetic_orchestrator


def test_named_entities_ignores_plain_words_and_acronyms() -> None:
    text = "Which team owns PhotonIndex? Did INC-2026-04 impact PostgreSQL?"
    entities = named_entities(text)
    assert "PhotonIndex" in entities
    assert "PostgreSQL" in entities
    # Sentence-initial words and all-caps incident ids are not names.
    assert "Which" not in entities
    assert "INC" not in entities


def test_named_entities_extracts_single_word_contextual_services() -> None:
    text = "Which team owns the Reconciler? Did Payments service fail?"
    entities = named_entities(text)
    assert "Reconciler" in entities
    assert "Payments" in entities
    assert "Which" not in entities


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
    now = datetime(2026, 3, 1, tzinfo=UTC)
    prov = Provenance.from_document("corpus/rfc_001.md")
    chunk = Chunk(
        chunk_id="chk_eventstream_01",
        doc_id="doc_eventstream",
        index=0,
        text="EventStream targets a p99 latency of 33ms and provides stream ingestion.",
        tokens=12,
        acl_scope=ACLScope.public(),
        ingested_at=now,
        provenance=prov,
    )
    orchestrator, _ = build_hermetic_orchestrator([chunk])
    orchestrator.exact_cache.clear()

    state = await orchestrator.run(query="Which team owns PhotonIndex?")

    assert state["is_abstention"]
    assert "sufficient information" in state["answer"]
    assert state["citations_valid"]
