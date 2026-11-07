from datetime import UTC, datetime

from app.core.acl import ACLScope
from app.domain import Chunk, Entity, Provenance, Relation, TemporalBounds
from app.evaluation.retrieval_metrics import ndcg_at_k, recall_at_k
from app.retrieval.filters import RetrievalFilter
from tests.fakes.in_memory_retrievers import (
    FakeBM25Retriever as BM25Retriever,
    FakeDenseRetriever as DenseRetriever,
    FakeGraphRetriever as GraphRetriever,
    FakeHybridRetriever as HybridRetriever,
)


def create_sample_chunks() -> list[Chunk]:
    now = datetime(2026, 3, 1, tzinfo=UTC)
    prov = Provenance.from_document("corpus/rfc_001.md")
    acl_public = ACLScope.public(tenant_id="default")
    acl_restricted = ACLScope.restricted(
        allowed_roles={"sre_lead"},
        tenant_id="default",
    )

    c1 = Chunk(
        chunk_id="chunk_storage_01",
        doc_id="doc_rfc_storage_001",
        index=0,
        text="PostgreSQL 16 acts as the single source of truth and outbox mechanism.",
        tokens=12,
        acl_scope=acl_public,
        temporal=TemporalBounds(valid_from=now),
        provenance=prov,
    )
    c2 = Chunk(
        chunk_id="chunk_vector_02",
        doc_id="doc_rfc_storage_001",
        index=1,
        text="Qdrant provides vector search indexing dense semantic embeddings and BM25.",
        tokens=12,
        acl_scope=acl_public,
        temporal=TemporalBounds(valid_from=now),
        provenance=prov,
    )
    c3 = Chunk(
        chunk_id="chunk_incident_03",
        doc_id="doc_postmortem_inc_04",
        index=0,
        text="Incident INC-2026-04 degraded PaymentGateway with a 24% failure rate.",
        tokens=11,
        acl_scope=acl_public,
        temporal=TemporalBounds(valid_from=datetime(2026, 4, 12, tzinfo=UTC)),
        provenance=prov,
    )
    c4 = Chunk(
        chunk_id="chunk_secret_04",
        doc_id="doc_secret_audit",
        index=0,
        text="Internal security incident postmortem details for SRE lead only.",
        tokens=10,
        acl_scope=acl_restricted,
        temporal=TemporalBounds(valid_from=now),
        provenance=prov,
    )
    return [c1, c2, c3, c4]


def test_sparse_bm25_exact_code_matching() -> None:
    chunks = create_sample_chunks()
    bm25 = BM25Retriever()
    bm25.index_chunks(chunks)

    # Search for an exact incident code
    results = bm25.search("What happened during INC-2026-04?", top_k=2)
    assert len(results) > 0
    top_chunk_id, score = results[0]
    assert top_chunk_id == "chunk_incident_03"
    assert score > 0.0


def test_dense_vector_semantic_search() -> None:
    chunks = create_sample_chunks()
    dense = DenseRetriever()
    dense.index_chunks(chunks)

    # Search conceptually for high-dimensional vector search
    results = dense.search("vector embeddings search database", top_k=2)
    assert len(results) > 0
    top_chunk_id, sim = results[0]
    assert top_chunk_id == "chunk_vector_02"
    assert sim > 0.0


def test_hybrid_reciprocal_rank_fusion() -> None:
    chunks = create_sample_chunks()
    hybrid = HybridRetriever()
    hybrid.index_chunks(chunks)

    query = "PostgreSQL source of truth outbox"
    evidence = hybrid.search(query=query, top_k=3)

    assert len(evidence) > 0
    assert evidence[0].chunk_id == "chunk_storage_01"
    assert evidence[0].retrieval_method == "hybrid"

    # Evaluate retrieval metrics
    retrieved_ids = [e.chunk_id for e in evidence]
    targets = {"chunk_storage_01"}
    recall = recall_at_k(retrieved_ids, targets, k=1)
    ndcg = ndcg_at_k(retrieved_ids, targets, k=1)

    assert recall == 1.0
    assert ndcg == 1.0


def test_retrieval_acl_and_temporal_prefiltering() -> None:
    chunks = create_sample_chunks()
    hybrid = HybridRetriever()
    hybrid.index_chunks(chunks)

    # 1. Unprivileged user cannot retrieve chunk_secret_04
    unprivileged_filter = RetrievalFilter(
        user_roles=frozenset({"junior_dev"}),
        is_admin=False,
    )
    evidence_public = hybrid.search(
        query="security audit postmortem",
        top_k=5,
        filter_criteria=unprivileged_filter,
    )
    retrieved_ids = {e.chunk_id for e in evidence_public}
    assert "chunk_secret_04" not in retrieved_ids

    # 2. Privileged SRE lead CAN retrieve chunk_secret_04
    privileged_filter = RetrievalFilter(
        user_roles=frozenset({"sre_lead"}),
        is_admin=False,
    )
    evidence_priv = hybrid.search(
        query="security audit postmortem",
        top_k=5,
        filter_criteria=privileged_filter,
    )
    priv_ids = {e.chunk_id for e in evidence_priv}
    assert "chunk_secret_04" in priv_ids

    # 3. Temporal filtering: as_of_time in March 2026 cannot see April 2026 incident
    march_filter = RetrievalFilter(
        as_of_time=datetime(2026, 3, 15, tzinfo=UTC),
    )
    march_evidence = hybrid.search(
        query="INC-2026-04 payment degradation",
        top_k=5,
        filter_criteria=march_filter,
    )
    march_ids = {e.chunk_id for e in march_evidence}
    assert "chunk_incident_03" not in march_ids


def test_graph_multi_hop_path_traversal() -> None:
    now = TemporalBounds.current()
    prov = Provenance.from_document("corpus/sample.md")
    acl = ACLScope.public()

    # Build knowledge graph:
    # Bob Kumar -[COMMANDED]-> INC-2026-04 -[IMPACTED]-> PaymentGateway
    # -[OWNED_BY]-> Payments Team -[LED_BY]-> Elena Rostova
    e1 = Entity(
        entity_id="ent_bob",
        name="Bob Kumar",
        entity_type="PERSON",
        acl_scope=acl,
        temporal=now,
        provenance=prov,
    )
    e2 = Entity(
        entity_id="ent_inc",
        name="INC-2026-04",
        entity_type="INCIDENT",
        acl_scope=acl,
        temporal=now,
        provenance=prov,
    )
    e3 = Entity(
        entity_id="ent_pg",
        name="PaymentGateway",
        entity_type="SERVICE",
        source_chunk_ids=["chunk_incident_03"],
        acl_scope=acl,
        temporal=now,
        provenance=prov,
    )
    e4 = Entity(
        entity_id="ent_team",
        name="Payments Team",
        entity_type="TEAM",
        acl_scope=acl,
        temporal=now,
        provenance=prov,
    )
    e5 = Entity(
        entity_id="ent_elena",
        name="Elena Rostova",
        entity_type="PERSON",
        acl_scope=acl,
        temporal=now,
        provenance=prov,
    )

    entities = [e1, e2, e3, e4, e5]
    relations = [
        Relation(
            relation_id="r1",
            source_entity_id=e1.entity_id,
            target_entity_id=e2.entity_id,
            relation_type="COMMANDED",
            acl_scope=acl,
            temporal=now,
            provenance=prov,
        ),
        Relation(
            relation_id="r2",
            source_entity_id=e2.entity_id,
            target_entity_id=e3.entity_id,
            relation_type="IMPACTED",
            acl_scope=acl,
            temporal=now,
            provenance=prov,
        ),
        Relation(
            relation_id="r3",
            source_entity_id=e3.entity_id,
            target_entity_id=e4.entity_id,
            relation_type="OWNED_BY",
            acl_scope=acl,
            temporal=now,
            provenance=prov,
        ),
        Relation(
            relation_id="r4",
            source_entity_id=e4.entity_id,
            target_entity_id=e5.entity_id,
            relation_type="LED_BY",
            acl_scope=acl,
            temporal=now,
            provenance=prov,
        ),
    ]

    graph_retriever = GraphRetriever()
    graph_retriever.index_graph(
        entities=entities, relations=relations, chunks=create_sample_chunks()
    )

    # Find multi-hop path from Bob Kumar to Elena Rostova
    path = graph_retriever.find_path("Bob Kumar", "Elena Rostova", max_depth=5)
    assert path is not None
    expected = [
        "Bob Kumar",
        "COMMANDED",
        "INC-2026-04",
        "IMPACTED",
        "PaymentGateway",
        "OWNED_BY",
        "Payments Team",
        "LED_BY",
        "Elena Rostova",
    ]
    assert path == expected

    # Convert path to supporting evidence
    evidence = graph_retriever.retrieve_path_evidence(path)
    assert len(evidence) > 0
    assert evidence[0].chunk_id == "chunk_incident_03"
    assert evidence[0].retrieval_method == "graph"
    assert evidence[0].path == expected
