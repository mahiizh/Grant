from datetime import UTC, datetime

from app.core.acl import ACLScope
from app.domain import Chunk, Entity, Provenance, Relation, TemporalBounds
from app.ingestion.chunking import chunk_parsed_document
from app.ingestion.conflicts import (
    close_superseded_chunks_in_memory,
    extract_document_root_and_version,
)
from app.ingestion.parse import parse_markdown
from app.retrieval.filters import RetrievalFilter
from tests.fakes.in_memory_retrievers import (
    FakeBM25Retriever,
    FakeDenseRetriever,
    FakeGraphRetriever,
    FakeHybridRetriever,
)


def test_extract_document_root_and_version() -> None:
    assert extract_document_root_and_version("doc_sla_payments_v2") == ("doc_sla_payments", 2)
    assert extract_document_root_and_version("doc_sla_payments_v1") == ("doc_sla_payments", 1)
    assert extract_document_root_and_version("doc_rfc_001") == ("doc_rfc_001", 1)
    assert extract_document_root_and_version("doc_service_eventstream") == (
        "doc_service_eventstream",
        1,
    )


def test_parsed_document_and_chunks_preserve_valid_to() -> None:
    doc_text = """---
title: Service Level Agreement: Payments API v1
doc_id: doc_sla_payments_v1
valid_from: 2026-01-01T00:00:00Z
valid_to: 2026-03-15T00:00:00Z
---
# SLA Payments v1
The p99 latency SLA for payment authorization is strictly 50ms.
"""
    parsed = parse_markdown(doc_text, source_path="sla_v1.md")
    assert parsed.valid_to == datetime(2026, 3, 15, 0, 0, tzinfo=UTC)

    chunks = chunk_parsed_document(parsed, source_uri="sla_v1.md")
    assert len(chunks) > 0
    assert chunks[0].temporal.valid_to == datetime(2026, 3, 15, 0, 0, tzinfo=UTC)


def test_close_superseded_chunks_in_memory() -> None:
    prov = Provenance.from_document("sla.md")
    acl = ACLScope.public()

    c1 = Chunk(
        chunk_id="chk_sla_v1_01",
        doc_id="doc_sla_payments_v1",
        index=0,
        text="p99 is 50ms",
        tokens=5,
        acl_scope=acl,
        temporal=TemporalBounds(valid_from=datetime(2026, 1, 1, tzinfo=UTC), valid_to=None),
        provenance=prov,
    )
    chunks = [c1]

    # Ingest v2 effective 2026-03-15
    closed = close_superseded_chunks_in_memory(
        chunks=chunks,
        new_doc_id="doc_sla_payments_v2",
        new_valid_from=datetime(2026, 3, 15, tzinfo=UTC),
    )

    assert "doc_sla_payments_v1" in closed
    assert chunks[0].temporal.valid_to == datetime(2026, 3, 15, tzinfo=UTC)


def test_temporal_as_of_filtering_across_all_branches() -> None:
    prov = Provenance.from_document("sla.md")
    acl = ACLScope.public()

    t_v1 = TemporalBounds(
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_to=datetime(2026, 3, 15, tzinfo=UTC),
    )
    t_v2 = TemporalBounds(
        valid_from=datetime(2026, 3, 15, tzinfo=UTC),
        valid_to=None,
    )

    chunk_v1 = Chunk(
        chunk_id="chk_sla_v1_001",
        doc_id="doc_sla_payments_v1",
        index=0,
        text="The p99 latency SLA for payment authorization is strictly 50ms under Payments v1.",
        tokens=15,
        acl_scope=acl,
        temporal=t_v1,
        provenance=prov,
    )
    chunk_v2 = Chunk(
        chunk_id="chk_sla_v2_001",
        doc_id="doc_sla_payments_v2",
        index=0,
        text="The p99 latency SLA for payment authorization is strictly 25ms under Payments v2.",
        tokens=15,
        acl_scope=acl,
        temporal=t_v2,
        provenance=prov,
    )

    all_chunks = [chunk_v1, chunk_v2]

    # Setup retrievers
    dense = FakeDenseRetriever()
    dense.index_chunks(all_chunks)

    sparse = FakeBM25Retriever()
    sparse.index_chunks(all_chunks)

    hybrid = FakeHybridRetriever(dense=dense, sparse=sparse)
    hybrid.index_chunks(all_chunks)

    # Graph
    e1 = Entity(
        entity_id="ent_sla",
        name="PaymentsSLA",
        entity_type="CONCEPT",
        acl_scope=acl,
        temporal=TemporalBounds.current(),
        provenance=prov,
        source_chunk_ids=["chk_sla_v1_001", "chk_sla_v2_001"],
    )
    r_v1 = Relation(
        relation_id="rel_v1",
        source_entity_id="ent_sla",
        target_entity_id="ent_sla",
        relation_type="DEFINES_LATENCY",
        acl_scope=acl,
        temporal=t_v1,
        provenance=prov,
    )
    r_v2 = Relation(
        relation_id="rel_v2",
        source_entity_id="ent_sla",
        target_entity_id="ent_sla",
        relation_type="DEFINES_LATENCY",
        acl_scope=acl,
        temporal=t_v2,
        provenance=prov,
    )
    graph = FakeGraphRetriever()
    graph.index_graph(entities=[e1], relations=[r_v1, r_v2], chunks=all_chunks)

    query = "What is the p99 latency SLA for payment authorization?"

    # --- Scenario 1: Query as of 2026-04-01 (after v2 is active) ---
    as_of_april = datetime(2026, 4, 1, 0, 0, tzinfo=UTC)
    filter_april = RetrievalFilter(acl_scope=acl, as_of_time=as_of_april)

    # 1. Dense branch must return v2, NO v1
    dense_res = dense.search(query, top_k=5, filter_criteria=filter_april)
    dense_ids = [cid for cid, _ in dense_res]
    assert "chk_sla_v1_001" not in dense_ids
    assert "chk_sla_v2_001" in dense_ids

    # 2. Sparse branch must return v2, NO v1
    sparse_res = sparse.search(query, top_k=5, filter_criteria=filter_april)
    sparse_ids = [cid for cid, _ in sparse_res]
    assert "chk_sla_v1_001" not in sparse_ids
    assert "chk_sla_v2_001" in sparse_ids

    # 3. Hybrid search must return v2, NO v1
    hybrid_res = hybrid.search(query, top_k=5, filter_criteria=filter_april)
    hybrid_ids = [ev.chunk_id for ev in hybrid_res]
    assert "chk_sla_v1_001" not in hybrid_ids
    assert "chk_sla_v2_001" in hybrid_ids

    # 4. Graph evidence retrieval must return v2, NO v1
    graph_res = graph.retrieve_path_evidence(["PaymentsSLA"], top_k=5, filter_criteria=filter_april)
    graph_ids = [ev.chunk_id for ev in graph_res]
    assert "chk_sla_v1_001" not in graph_ids
    assert "chk_sla_v2_001" in graph_ids

    # --- Scenario 2: Query as of 2026-02-01 (when v1 was active) ---
    as_of_feb = datetime(2026, 2, 1, 0, 0, tzinfo=UTC)
    filter_feb = RetrievalFilter(acl_scope=acl, as_of_time=as_of_feb)

    # Dense branch must return v1, NO v2
    feb_dense = dense.search(query, top_k=5, filter_criteria=filter_feb)
    feb_dense_ids = [cid for cid, _ in feb_dense]
    assert "chk_sla_v1_001" in feb_dense_ids
    assert "chk_sla_v2_001" not in feb_dense_ids

    # Sparse branch must return v1, NO v2
    feb_sparse = sparse.search(query, top_k=5, filter_criteria=filter_feb)
    feb_sparse_ids = [cid for cid, _ in feb_sparse]
    assert "chk_sla_v1_001" in feb_sparse_ids
    assert "chk_sla_v2_001" not in feb_sparse_ids

    # Hybrid must return v1, NO v2
    feb_hybrid = hybrid.search(query, top_k=5, filter_criteria=filter_feb)
    feb_hybrid_ids = [ev.chunk_id for ev in feb_hybrid]
    assert "chk_sla_v1_001" in feb_hybrid_ids
    assert "chk_sla_v2_001" not in feb_hybrid_ids
