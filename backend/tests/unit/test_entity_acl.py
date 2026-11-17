from datetime import UTC, datetime

import pytest

from app.core.acl import ACLScope
from app.domain import Chunk, Entity, Provenance, Relation, TemporalBounds
from app.retrieval.filters import RetrievalFilter
from tests.fakes.in_memory_indexers import FakeNeo4jIndexer
from tests.fakes.in_memory_retrievers import FakeGraphRetriever


def test_acl_scope_union() -> None:
    scope_restricted = ACLScope.restricted(allowed_roles={"security", "audit"})
    scope_public = ACLScope.public()

    union_scope = scope_restricted.union(scope_public)
    assert union_scope.is_public is True
    assert "security" in union_scope.allowed_roles

    # Unauthenticated/public user permits
    assert union_scope.permits(user_roles=frozenset()) is True

    # Two disjoint restricted scopes
    scope_a = ACLScope.restricted(allowed_roles={"engineering"})
    scope_b = ACLScope.restricted(allowed_roles={"finance"}, allowed_groups={"cfo-office"})
    merged = scope_a.union(scope_b)
    assert merged.is_public is False
    assert merged.permits(user_roles=frozenset({"hr"})) is False
    assert merged.permits(user_roles=frozenset({"engineering"})) is True
    assert merged.permits(user_roles=frozenset({"finance"})) is True
    assert merged.permits(user_roles=frozenset(), user_groups=frozenset({"cfo-office"})) is True


def test_entity_acl_leak_restricted_ingested_before_public() -> None:
    """Security leak test:

    Ingest a restricted doc before a public doc that mention the same entity.
    A user without access must see the shared entity, but MUST NOT see the
    restricted edges, chunks, or path hops.
    """
    prov = Provenance.from_document("security_test.md")
    t = TemporalBounds(valid_from=datetime(2026, 1, 1, tzinfo=UTC), valid_to=None)

    acl_restricted = ACLScope.restricted(allowed_roles={"admin"})
    acl_public = ACLScope.public()

    # 1. Restricted Document Chunks, Entities, and Edges (Ingested First)
    chk_restricted = Chunk(
        chunk_id="chk_sec_001",
        doc_id="doc_restricted_vault",
        index=0,
        text="The Master Key is stored inside the Hardware HSM Vault.",
        tokens=12,
        acl_scope=acl_restricted,
        temporal=t,
        provenance=prov,
    )

    ent_shared_res = Entity(
        entity_id="ent_vault",
        name="HSM Vault",
        entity_type="SYSTEM",
        acl_scope=acl_restricted,
        temporal=t,
        provenance=prov,
        source_chunk_ids=["chk_sec_001"],
    )

    ent_secret = Entity(
        entity_id="ent_key",
        name="Master Key",
        entity_type="SECRET",
        acl_scope=acl_restricted,
        temporal=t,
        provenance=prov,
        source_chunk_ids=["chk_sec_001"],
    )

    rel_secret = Relation(
        relation_id="rel_sec_001",
        source_entity_id="ent_vault",
        target_entity_id="ent_key",
        relation_type="PROTECTS",
        acl_scope=acl_restricted,
        temporal=t,
        provenance=prov,
        source_chunk_ids=["chk_sec_001"],
    )

    # 2. Public Document Chunks, Entities, and Edges (Ingested Second)
    chk_public = Chunk(
        chunk_id="chk_pub_001",
        doc_id="doc_public_overview",
        index=0,
        text="Our HSM Vault is certified for FIPS 140-2 Level 3 compliance.",
        tokens=14,
        acl_scope=acl_public,
        temporal=t,
        provenance=prov,
    )

    ent_shared_pub = Entity(
        entity_id="ent_vault",
        name="HSM Vault",
        entity_type="SYSTEM",
        acl_scope=acl_public,
        temporal=t,
        provenance=prov,
        source_chunk_ids=["chk_pub_001"],
    )

    ent_public = Entity(
        entity_id="ent_compliance",
        name="FIPS Compliance",
        entity_type="STANDARD",
        acl_scope=acl_public,
        temporal=t,
        provenance=prov,
        source_chunk_ids=["chk_pub_001"],
    )

    rel_public = Relation(
        relation_id="rel_pub_001",
        source_entity_id="ent_vault",
        target_entity_id="ent_compliance",
        relation_type="COMPLIES_WITH",
        acl_scope=acl_public,
        temporal=t,
        provenance=prov,
        source_chunk_ids=["chk_pub_001"],
    )

    # Ingest in exact order: Restricted BEFORE Public
    entities = [ent_shared_res, ent_secret, ent_shared_pub, ent_public]
    relations = [rel_secret, rel_public]
    chunks = [chk_restricted, chk_public]

    graph = FakeGraphRetriever()
    graph.index_graph(entities=entities, relations=relations, chunks=chunks)

    # Caller without admin access (public user)
    filter_public = RetrievalFilter(acl_scope=acl_public, user_roles=frozenset())

    # --- Node Visibility Checks ---
    # Public user CAN see the shared entity because public doc mentions it
    matches = graph.search_entities("HSM Vault", filter_criteria=filter_public)
    assert len(matches) == 1
    assert matches[0]["name"] == "HSM Vault"

    # Public user CAN see the public entity
    pub_matches = graph.search_entities("FIPS Compliance", filter_criteria=filter_public)
    assert len(pub_matches) == 1

    # Public user CANNOT see the secret entity
    secret_matches = graph.search_entities("Master Key", filter_criteria=filter_public)
    assert len(secret_matches) == 0

    # --- Edge & Path Hop Checks ---
    # Public user CAN traverse the public edge
    pub_path = graph.find_path("HSM Vault", "FIPS Compliance", filter_criteria=filter_public)
    assert pub_path is not None
    assert list(pub_path) == ["HSM Vault", "COMPLIES_WITH", "FIPS Compliance"]

    # Public user CANNOT traverse the restricted edge to Master Key
    secret_path = graph.find_path("HSM Vault", "Master Key", filter_criteria=filter_public)
    assert secret_path is None

    # --- Chunk Evidence Retrieval Checks ---
    # Evidence retrieved for the shared entity MUST NOT contain the restricted chunk
    evidence = graph.retrieve_path_evidence(["HSM Vault"], filter_criteria=filter_public)
    evidence_chunk_ids = {ev.chunk_id for ev in evidence}
    assert "chk_sec_001" not in evidence_chunk_ids
    assert "chk_pub_001" in evidence_chunk_ids

    # --- Admin Verification (Non-vacuity) ---
    filter_admin = RetrievalFilter(acl_scope=acl_public, user_roles=frozenset({"admin"}))
    admin_secret = graph.search_entities("Master Key", filter_criteria=filter_admin)
    assert len(admin_secret) == 1

    admin_path = graph.find_path("HSM Vault", "Master Key", filter_criteria=filter_admin)
    assert admin_path is not None
    assert list(admin_path) == ["HSM Vault", "PROTECTS", "Master Key"]

    admin_evidence = graph.retrieve_path_evidence(["HSM Vault"], filter_criteria=filter_admin)
    admin_chunk_ids = {ev.chunk_id for ev in admin_evidence}
    assert "chk_sec_001" in admin_chunk_ids
    assert "chk_pub_001" in admin_chunk_ids


@pytest.mark.asyncio
async def test_fake_neo4j_indexer_recompute_and_delete() -> None:
    """Verify Neo4j indexer scope union on ingest and recompute/cleanup on delete."""
    indexer = FakeNeo4jIndexer()

    # 1. Ingest restricted chunk & node
    await indexer.merge_chunk(
        chunk_id="c_res_1",
        doc_id="doc_res",
        text="Restricted text",
        acl_scope={"tenant_id": "default", "is_public": False, "allowed_roles": ["finance"]},
    )
    await indexer.merge_node(
        entity_id="e_corp",
        name="AcmeCorp",
        entity_type="Company",
        acl_scope={"tenant_id": "default", "is_public": False, "allowed_roles": ["finance"]},
        properties={"doc_id": "doc_res"},
    )
    await indexer.link_chunk_entity("c_res_1", "e_corp")

    node = indexer._nodes["e_corp"]
    assert node["acl_is_public"] is False
    assert "finance" in node["acl_allowed_roles"]

    # 2. Ingest public chunk & node mentioning the same entity
    await indexer.merge_chunk(
        chunk_id="c_pub_1",
        doc_id="doc_pub",
        text="Public text",
        acl_scope={"tenant_id": "default", "is_public": True, "allowed_roles": []},
    )
    await indexer.merge_node(
        entity_id="e_corp",
        name="AcmeCorp",
        entity_type="Company",
        acl_scope={"tenant_id": "default", "is_public": True, "allowed_roles": []},
        properties={"doc_id": "doc_pub"},
    )
    await indexer.link_chunk_entity("c_pub_1", "e_corp")

    node = indexer._nodes["e_corp"]
    # Entity must now be visible publicly because public doc mentions it
    assert node["acl_is_public"] is True
    assert "finance" in node["acl_allowed_roles"]

    # 3. Delete the public doc
    await indexer.delete_by_doc_id("doc_pub")
    # Entity must now revert to restricted because only doc_res mentions it!
    node = indexer._nodes["e_corp"]
    assert node["acl_is_public"] is False
    assert "finance" in node["acl_allowed_roles"]

    # 4. Delete the restricted doc
    await indexer.delete_by_doc_id("doc_res")
    # Entity was solely mentioned by these two docs, so it must be deleted
    assert "e_corp" not in indexer._nodes
