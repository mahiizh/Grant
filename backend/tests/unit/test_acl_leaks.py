from typing import cast

import pytest

from app.core.auth import AuthenticatedUser
from app.core.config import get_settings
from app.domain import Answer, Evidence, Provenance
from app.retrieval.filters import RetrievalFilter
from tests.fakes.hermetic import build_hermetic_orchestrator, load_corpus_chunks
from tests.fakes.in_memory_cache import FakeExactCache, FakeSemanticCache
from tests.fakes.in_memory_retrievers import (
    FakeBM25Retriever,
    FakeDenseRetriever,
    FakeGraphRetriever,
    FakeHybridRetriever,
    FakeReranker,
)

DATA_PLATFORM_DOCS = {
    "doc_team_directory_2026",
    "doc_rfc_001",
    "doc_rfc_004",
    "doc_dual_write_consistency",
}
QUERY = "Data Platform Team PostgreSQL outbox ownership"


def _user_filter(username: str, scope: str | None = None) -> RetrievalFilter:
    user = AuthenticatedUser(username, get_settings().DEV_USERS[username])
    return user.to_retrieval_filter(scope)


def _assert_no_data_platform(doc_ids: set[str]) -> None:
    leaked = doc_ids & DATA_PLATFORM_DOCS
    assert not leaked, f"ACL leak: bob retrieved data-platform docs {sorted(leaked)}"


def test_dense_and_sparse_retrievers_do_not_leak() -> None:
    chunks = load_corpus_chunks()
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    dense = FakeDenseRetriever()
    dense.index_chunks(chunks)
    sparse = FakeBM25Retriever()
    sparse.index_chunks(chunks)

    bob = _user_filter("bob")
    alice = _user_filter("alice")

    for retriever in (dense, sparse):
        bob_docs = {
            by_id[cid].doc_id for cid, _ in retriever.search(QUERY, top_k=45, filter_criteria=bob)
        }
        _assert_no_data_platform(bob_docs)

        # Non-vacuity: alice really can retrieve the data-platform docs for this query.
        alice_docs = {
            by_id[cid].doc_id for cid, _ in retriever.search(QUERY, top_k=45, filter_criteria=alice)
        }
        assert alice_docs & DATA_PLATFORM_DOCS


def test_hybrid_rerank_does_not_leak() -> None:
    chunks = load_corpus_chunks()
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    dense = FakeDenseRetriever()
    sparse = FakeBM25Retriever()
    reranker = FakeReranker()
    hybrid = FakeHybridRetriever(dense=dense, sparse=sparse, reranker=reranker)
    hybrid.index_chunks(chunks)

    evidence = hybrid.search(
        QUERY,
        top_k=10,
        filter_criteria=_user_filter("bob"),
        rerank=True,
    )

    _assert_no_data_platform({item.doc_id for item in evidence})
    reranker_docs = {by_id[cid].doc_id for cid in reranker.seen_chunk_ids}
    _assert_no_data_platform(reranker_docs)


def test_graph_path_and_evidence_do_not_leak() -> None:
    orchestrator, _ = build_hermetic_orchestrator(load_corpus_chunks())
    graph = cast(FakeGraphRetriever, orchestrator.graph_retriever)
    bob = _user_filter("bob")

    # A path to a payments-only entity must not be found for bob.
    assert graph.find_path("Bob Kumar", "Elena Rostova", filter_criteria=bob) is None

    path = graph.find_path("Bob Kumar", "INC-2026-04", filter_criteria=bob)
    assert path is not None
    evidence = graph.retrieve_path_evidence(list(path), filter_criteria=bob)
    _assert_no_data_platform({item.doc_id for item in evidence})


def test_cache_does_not_cross_acl_boundaries() -> None:
    alice = _user_filter("alice")
    bob = _user_filter("bob")
    leaky_answer = Answer(
        query=QUERY,
        answer="Alice Chen leads the Data Platform Team.",
        evidence=[
            Evidence(
                chunk_id="chk_doc_team_directory_2026_0001_fc8d82e177",
                doc_id="doc_team_directory_2026",
                text="Data Platform Team lead: Alice Chen.",
                score=1.0,
                retrieval_method="hybrid",
                provenance=Provenance.from_document("corpus/team_directory_2026.md"),
            )
        ],
    )

    exact = FakeExactCache()
    semantic = FakeSemanticCache(similarity_threshold=0.0)
    exact.set(QUERY, leaky_answer, alice.acl_scope)
    semantic.set(QUERY, leaky_answer, alice.acl_scope)

    # Alice hits her own entry; bob must miss both caches.
    assert exact.get(QUERY, alice.acl_scope) is not None
    assert semantic.get(QUERY, alice.acl_scope) is not None
    assert exact.get(QUERY, bob.acl_scope) is None
    assert semantic.get(QUERY, bob.acl_scope) is None


@pytest.mark.asyncio
async def test_orchestrator_end_to_end_does_not_leak() -> None:
    orchestrator, _ = build_hermetic_orchestrator(load_corpus_chunks())
    bob_scope = AuthenticatedUser("bob", get_settings().DEV_USERS["bob"]).to_acl_scope()

    state = await orchestrator.run(
        query="Who leads the Data Platform Team and what systems do they own?",
        acl_scope=bob_scope,
    )

    _assert_no_data_platform({item.doc_id for item in state.get("evidence", [])})
