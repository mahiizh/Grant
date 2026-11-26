from datetime import UTC, datetime

import pytest

from app.core.acl import ACLScope
from app.domain import Chunk, Entity, Provenance, Relation
from app.retrieval.filters import RetrievalFilter
from tests.fakes.in_memory_indexers import FakeNeo4jIndexer
from tests.fakes.in_memory_retrievers import FakeGraphRetriever


def test_acl_scope_union_never_widens_to_public() -> None:
    owner_scope = ACLScope.owner("alice")
    public_scope = ACLScope.public()

    merged = owner_scope.union(public_scope)
    assert merged == owner_scope
    assert not merged.permits(owner_user_id="bob")

    shared_a = ACLScope.shared("shared-analytics")
    shared_b = ACLScope.shared("shared-finance")
    merged_shared = shared_a.union(shared_b)
    assert merged_shared.shared_scope == "shared-analytics"
    assert merged_shared.permits(shared_scopes={"shared-analytics"})
    assert not merged_shared.permits(shared_scopes={"shared-finance"})


def test_entity_acl_leak_owner_ingested_before_shared() -> None:
    """A caller with a shared scope sees shared nodes/edges, never another owner's."""
    prov = Provenance.from_document("security_test.md")
    ingested_at = datetime(2026, 1, 1, tzinfo=UTC)

    acl_shared = ACLScope.shared("shared-operations")
    acl_secret = ACLScope.owner("bob")

    # Shared document chunk, entities, and edge.
    chk_shared = Chunk(
        chunk_id="chk_shared_001",
        doc_id="doc_shared_overview",
        index=0,
        text="Our HSM Vault is certified for FIPS 140-2 Level 3 compliance.",
        tokens=14,
        acl_scope=acl_shared,
        ingested_at=ingested_at,
        provenance=prov,
    )
    ent_vault = Entity(
        entity_id="ent_vault",
        name="HSM Vault",
        entity_type="SYSTEM",
        acl_scope=acl_shared,
        ingested_at=ingested_at,
        provenance=prov,
        source_chunk_ids=["chk_shared_001"],
    )
    ent_public = Entity(
        entity_id="ent_compliance",
        name="FIPS Compliance",
        entity_type="STANDARD",
        acl_scope=acl_shared,
        ingested_at=ingested_at,
        provenance=prov,
        source_chunk_ids=["chk_shared_001"],
    )
    rel_public = Relation(
        relation_id="rel_shared_001",
        source_entity_id="ent_vault",
        target_entity_id="ent_compliance",
        relation_type="COMPLIES_WITH",
        acl_scope=acl_shared,
        ingested_at=ingested_at,
        provenance=prov,
        source_chunk_ids=["chk_shared_001"],
    )

    # Another user's private chunk, entity, and edge.
    chk_secret = Chunk(
        chunk_id="chk_secret_001",
        doc_id="doc_bob_vault",
        index=0,
        text="The Master Key is stored inside the Hardware HSM Vault.",
        tokens=12,
        acl_scope=acl_secret,
        ingested_at=ingested_at,
        provenance=prov,
    )
    ent_secret = Entity(
        entity_id="ent_key",
        name="Master Key",
        entity_type="SECRET",
        acl_scope=acl_secret,
        ingested_at=ingested_at,
        provenance=prov,
        source_chunk_ids=["chk_secret_001"],
    )
    rel_secret = Relation(
        relation_id="rel_secret_001",
        source_entity_id="ent_vault",
        target_entity_id="ent_key",
        relation_type="PROTECTS",
        acl_scope=acl_secret,
        ingested_at=ingested_at,
        provenance=prov,
        source_chunk_ids=["chk_secret_001"],
    )

    graph = FakeGraphRetriever()
    graph.index_graph(
        entities=[ent_vault, ent_public, ent_secret],
        relations=[rel_public, rel_secret],
        chunks=[chk_shared, chk_secret],
    )

    caller = RetrievalFilter(
        acl_scope=acl_shared,
        owner_user_id="alice",
    )

    assert len(graph.search_entities("HSM Vault", filter_criteria=caller)) == 1
    assert len(graph.search_entities("FIPS Compliance", filter_criteria=caller)) == 1
    assert len(graph.search_entities("Master Key", filter_criteria=caller)) == 0

    shared_path = graph.find_path("HSM Vault", "FIPS Compliance", filter_criteria=caller)
    assert shared_path is not None
    assert list(shared_path) == ["HSM Vault", "COMPLIES_WITH", "FIPS Compliance"]

    secret_path = graph.find_path("HSM Vault", "Master Key", filter_criteria=caller)
    assert secret_path is None

    evidence = graph.retrieve_path_evidence(["HSM Vault"], filter_criteria=caller)
    evidence_chunk_ids = {ev.chunk_id for ev in evidence}
    assert "chk_secret_001" not in evidence_chunk_ids
    assert "chk_shared_001" in evidence_chunk_ids

    admin = RetrievalFilter(acl_scope=ACLScope.public(), is_admin=True)
    assert len(graph.search_entities("Master Key", filter_criteria=admin)) == 1
    admin_path = graph.find_path("HSM Vault", "Master Key", filter_criteria=admin)
    assert admin_path is not None
    assert list(admin_path) == ["HSM Vault", "PROTECTS", "Master Key"]
    admin_chunks = {
        ev.chunk_id
        for ev in graph.retrieve_path_evidence(list(admin_path), filter_criteria=admin)
    }
    assert "chk_secret_001" in admin_chunks
    assert "chk_shared_001" in admin_chunks


@pytest.mark.asyncio
async def test_fake_neo4j_indexer_recompute_and_delete() -> None:
    """Verify the fake indexer tightens ACLs on ingest and relaxes them on delete."""
    indexer = FakeNeo4jIndexer()

    # 1. Public chunk and node.
    await indexer.merge_chunk(
        chunk_id="c_pub_1",
        doc_id="doc_pub",
        text="Public text",
        acl_scope={},
    )
    await indexer.merge_node(
        entity_id="e_corp",
        name="AcmeCorp",
        entity_type="Company",
        acl_scope={},
        properties={"doc_id": "doc_pub"},
    )
    await indexer.link_chunk_entity("c_pub_1", "e_corp")

    node = indexer._nodes["e_corp"]
    assert node["acl_is_public"] is True
    assert node["acl_owner_user_id"] == ""

    # 2. Another user's private chunk mentioning the same entity tightens it.
    await indexer.merge_chunk(
        chunk_id="c_res_1",
        doc_id="doc_res",
        text="Restricted text",
        acl_scope={"owner_user_id": "bob"},
    )
    await indexer.merge_node(
        entity_id="e_corp",
        name="AcmeCorp",
        entity_type="Company",
        acl_scope={"owner_user_id": "bob"},
        properties={"doc_id": "doc_res"},
    )
    await indexer.link_chunk_entity("c_res_1", "e_corp")

    node = indexer._nodes["e_corp"]
    assert node["acl_is_public"] is False
    assert node["acl_owner_user_id"] == "bob"
    assert "bob" in node["owner_user_ids"]
    assert "acl_allowed_roles" not in node

    # 3. Delete the private doc; the entity reverts to public.
    await indexer.delete_by_doc_id("doc_res")
    node = indexer._nodes["e_corp"]
    assert node["acl_is_public"] is True
    assert node["acl_owner_user_id"] == ""

    # 4. Delete the public doc; the orphaned entity is removed.
    await indexer.delete_by_doc_id("doc_pub")
    assert "e_corp" not in indexer._nodes
