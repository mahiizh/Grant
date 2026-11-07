from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.acl import ACLScope
from app.domain import (
    Answer,
    Chunk,
    Document,
    Entity,
    Evidence,
    Provenance,
    Relation,
    SourceTier,
    TemporalBounds,
    generate_chunk_id,
    generate_doc_id,
    generate_entity_id,
    generate_relation_id,
    normalize_entity_name,
)


def test_id_generation_determinism() -> None:
    doc_id1 = generate_doc_id("rfc_001_storage", version=1)
    doc_id2 = generate_doc_id("rfc_001_storage", version=1)
    assert doc_id1 == doc_id2
    assert doc_id1.startswith("doc_rfc_001_storage_")

    doc_id_v2 = generate_doc_id("rfc_001_storage", version=2)
    assert doc_id1 != doc_id_v2

    chunk_id1 = generate_chunk_id(doc_id1, 0, "PostgreSQL 16 is source of truth.")
    chunk_id2 = generate_chunk_id(doc_id1, 0, "PostgreSQL 16 is source of truth.")
    assert chunk_id1 == chunk_id2
    assert "0000" in chunk_id1

    ent_id1 = generate_entity_id("PostgreSQL 16", "DATABASE")
    ent_id2 = generate_entity_id(" postgresql 16 ", "DATABASE")
    assert ent_id1 == ent_id2
    assert ent_id1.startswith("ent_database_postgresql_16_")

    rel_id1 = generate_relation_id("ent_a", "STAGED_IN", "ent_b")
    rel_id2 = generate_relation_id("ent_a", "STAGED_IN", "ent_b")
    assert rel_id1 == rel_id2


def test_normalize_entity_name() -> None:
    assert normalize_entity_name("  PaymentGateway  ") == "paymentgateway"
    assert normalize_entity_name("Core-Banking Service!") == "core-banking_service"


def test_temporal_bounds_validity() -> None:
    t_base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    t_end = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)

    # Valid to before valid from should raise
    with pytest.raises(ValueError):
        TemporalBounds(valid_from=t_end, valid_to=t_base)

    bounds = TemporalBounds(valid_from=t_base, valid_to=t_end, source_version=1)
    # Target prior to valid_from
    assert not bounds.is_valid_at(datetime(2025, 12, 31, tzinfo=UTC))
    # Target within interval
    assert bounds.is_valid_at(datetime(2026, 3, 15, tzinfo=UTC))
    # Target at valid_from
    assert bounds.is_valid_at(t_base)
    # Target at or after valid_to
    assert not bounds.is_valid_at(t_end)
    assert not bounds.is_valid_at(datetime(2026, 7, 1, tzinfo=UTC))


def test_temporal_invalidation_and_overlap() -> None:
    t_start = datetime(2026, 1, 1, tzinfo=UTC)
    bounds_v1 = TemporalBounds.current(valid_from=t_start, source_version=1)

    t_inval = datetime(2026, 4, 1, tzinfo=UTC)
    bounds_v2 = bounds_v1.invalidate(invalidated_at=t_inval)

    assert bounds_v2.valid_to == t_inval
    assert bounds_v2.source_version == 2
    assert not bounds_v2.is_valid_at(datetime(2026, 5, 1, tzinfo=UTC))

    # Overlaps check
    b1 = TemporalBounds(
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_to=datetime(2026, 3, 1, tzinfo=UTC),
    )
    b2 = TemporalBounds(
        valid_from=datetime(2026, 2, 1, tzinfo=UTC),
        valid_to=datetime(2026, 4, 1, tzinfo=UTC),
    )
    b3 = TemporalBounds(
        valid_from=datetime(2026, 5, 1, tzinfo=UTC),
        valid_to=None,
    )

    assert b1.overlaps(b2)
    assert not b1.overlaps(b3)


def test_provenance_citation_rules() -> None:
    # Tier 1: Ingested doc
    doc_prov = Provenance.from_document(source_uri="corpus/rfc_001.md")
    assert doc_prov.tier == SourceTier.TIER_1_DOCUMENT
    assert doc_prov.verified
    assert doc_prov.can_cite()

    # Tier 2: Media agent
    agent_prov = Provenance.from_agent(source_uri="agent://media/session_1", confidence=0.8)
    assert agent_prov.can_cite(min_trust_to_cite=0.7)
    assert not agent_prov.can_cite(min_trust_to_cite=0.9)

    # Tier 3: Model recall
    recall_prov = Provenance.from_model_recall(model_name="gemini-1.5-pro", confidence=0.95)
    assert recall_prov.tier == SourceTier.TIER_3_MODEL_RECALL
    assert not recall_prov.verified
    # Crucial rule: Unverified model recall CANNOT be cited, despite 0.95 confidence
    assert not recall_prov.can_cite(min_trust_to_cite=0.7)

    # Promoting model recall
    promoted = recall_prov.promote("corpus/rfc_001.md#page=2")
    assert promoted.verified
    assert promoted.can_cite(min_trust_to_cite=0.7)


def test_acl_scope_enforcement() -> None:
    public_scope = ACLScope.public(tenant_id="tenant_a")
    assert public_scope.permits(user_roles=set(), tenant_id="tenant_a")
    # Wrong tenant rejected
    assert not public_scope.permits(user_roles=set(), tenant_id="tenant_b")

    restricted_scope = ACLScope.restricted(
        allowed_roles={"admin", "sre_lead"},
        tenant_id="tenant_a",
    )
    # Regular user denied
    assert not restricted_scope.permits(user_roles={"engineer"}, tenant_id="tenant_a")
    # Matching role permitted
    assert restricted_scope.permits(user_roles={"sre_lead"}, tenant_id="tenant_a")
    # Admin override permitted
    assert restricted_scope.permits(user_roles=set(), tenant_id="tenant_a", is_admin=True)


def test_domain_model_assembly() -> None:
    now = datetime.now(UTC)
    temporal = TemporalBounds.current(valid_from=now)
    prov = Provenance.from_document(source_uri="corpus/rfc_001.md")
    acl = ACLScope.public()

    chunk = Chunk(
        chunk_id="chunk_01",
        doc_id="doc_01",
        index=0,
        text="Sample text content.",
        tokens=4,
        acl_scope=acl,
        temporal=temporal,
        provenance=prov,
    )
    doc = Document(
        doc_id="doc_01",
        title="RFC 001",
        content="Sample text content.",
        chunks=[chunk],
        acl_scope=acl,
        temporal=temporal,
        provenance=prov,
    )
    entity = Entity(
        entity_id="ent_01",
        name="Postgres",
        entity_type="DATABASE",
        source_chunk_ids=[chunk.chunk_id],
        acl_scope=acl,
        temporal=temporal,
        provenance=prov,
    )
    rel = Relation(
        relation_id="rel_01",
        source_entity_id=entity.entity_id,
        target_entity_id="ent_02",
        relation_type="HOSTED_ON",
        source_chunk_ids=[chunk.chunk_id],
        acl_scope=acl,
        temporal=temporal,
        provenance=prov,
    )
    evidence = Evidence(
        chunk_id=chunk.chunk_id,
        doc_id=doc.doc_id,
        text=chunk.text,
        score=0.92,
        retrieval_method="hybrid",
        provenance=prov,
    )
    answer = Answer(
        query="Where is Postgres hosted?",
        answer="Postgres is hosted on ent_02.",
        evidence=[evidence],
        router_strategy="graph",
    )

    assert rel.relation_id == "rel_01"
    assert doc.chunks[0].chunk_id == "chunk_01"
    assert answer.evidence[0].score == 0.92
    assert not answer.is_abstention

    # Frozen models prevent inadvertent field mutations
    with pytest.raises(ValidationError):
        doc.title = "New Title"  # type: ignore[misc]
