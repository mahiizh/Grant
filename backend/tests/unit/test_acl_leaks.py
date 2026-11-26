from datetime import UTC, datetime

import pytest

from app.core.acl import ACLScope
from app.core.auth import AuthenticatedUser
from app.domain import Answer, Chunk, Entity, Evidence, Provenance, Relation
from app.retrieval.filters import RetrievalFilter
from tests.fakes.hermetic import build_hermetic_orchestrator
from tests.fakes.in_memory_cache import FakeExactCache
from tests.fakes.in_memory_retrievers import (
    FakeBM25Retriever,
    FakeDenseRetriever,
    FakeGraphRetriever,
    FakeHybridRetriever,
    FakeReranker,
)

QUERY = "latency ownership"
ALICE_PRIVATE_DOC = "doc_alice_private"
BOB_PRIVATE_DOC = "doc_bob_private"
SHARED_DOC = "doc_shared"
PUBLIC_DOC = "doc_public"
SHARED_SCOPE = "platform-oncall"


INGESTED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _chunk(
    chunk_id: str,
    doc_id: str,
    text: str,
    *,
    owner_user_id: str | None = None,
    shared_scope: str | None = None,
) -> Chunk:
    scope = ACLScope.shared(shared_scope) if shared_scope else ACLScope.public()
    return Chunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        index=0,
        text=text,
        owner_user_id=owner_user_id,
        acl_scope=scope,
        ingested_at=INGESTED_AT,
        provenance=Provenance.from_document(f"user_docs/{doc_id}.md"),
    )


@pytest.fixture
def chunks() -> list[Chunk]:
    return [
        _chunk(
            "chk_alice",
            ALICE_PRIVATE_DOC,
            "latency ownership belongs to alice",
            owner_user_id="alice",
        ),
        _chunk(
            "chk_bob",
            BOB_PRIVATE_DOC,
            "latency ownership belongs to bob",
            owner_user_id="bob",
        ),
        _chunk(
            "chk_shared",
            SHARED_DOC,
            "latency ownership belongs to platform oncall",
            shared_scope=SHARED_SCOPE,
        ),
        _chunk("chk_public", PUBLIC_DOC, "latency ownership is documented publicly"),
    ]


def _filter(
    owner_user_id: str | None = None,
    shared_scope: str | None = None,
    *,
    is_admin: bool = False,
) -> RetrievalFilter:
    return RetrievalFilter(
        acl_scope=ACLScope.shared(shared_scope) if shared_scope else ACLScope.public(),
        owner_user_id=owner_user_id,
        is_admin=is_admin,
    )


def _assert_isolated(doc_ids: set[str], viewer: str) -> None:
    forbidden = {
        "alice": {BOB_PRIVATE_DOC, SHARED_DOC},
        "bob": {ALICE_PRIVATE_DOC, SHARED_DOC},
        "anonymous": {ALICE_PRIVATE_DOC, BOB_PRIVATE_DOC, SHARED_DOC},
    }[viewer]
    leaked = doc_ids & forbidden
    assert not leaked, f"ACL leak for {viewer}: {sorted(leaked)}"


def test_dense_and_sparse_do_not_leak_private_or_shared(chunks: list[Chunk]) -> None:
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    dense = FakeDenseRetriever()
    sparse = FakeBM25Retriever()
    dense.index_chunks(chunks)
    sparse.index_chunks(chunks)

    for retriever in (dense, sparse):
        for viewer, criteria in (
            ("alice", _filter(owner_user_id="alice")),
            ("bob", _filter(owner_user_id="bob")),
            ("anonymous", _filter()),
        ):
            results = retriever.search(QUERY, top_k=20, filter_criteria=criteria)
            docs = {by_id[chunk_id].doc_id for chunk_id, _ in results}
            _assert_isolated(docs, viewer)
            assert PUBLIC_DOC in docs  # non-vacuous

        shared_results = retriever.search(
            QUERY, top_k=20, filter_criteria=_filter(shared_scope=SHARED_SCOPE)
        )
        assert SHARED_DOC in {by_id[chunk_id].doc_id for chunk_id, _ in shared_results}


def test_hybrid_rerank_does_not_leak(chunks: list[Chunk]) -> None:
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    reranker = FakeReranker()
    hybrid = FakeHybridRetriever(reranker=reranker)
    hybrid.index_chunks(chunks)

    evidence = hybrid.search(
        QUERY,
        top_k=10,
        filter_criteria=_filter(owner_user_id="bob"),
        rerank=True,
    )
    _assert_isolated({item.doc_id for item in evidence}, "bob")
    _assert_isolated(
        {by_id[chunk_id].doc_id for chunk_id in reranker.seen_chunk_ids},
        "bob",
    )
    assert PUBLIC_DOC in {item.doc_id for item in evidence}

    shared_evidence = hybrid.search(
        QUERY,
        top_k=10,
        filter_criteria=_filter(shared_scope=SHARED_SCOPE),
        rerank=True,
    )
    assert SHARED_DOC in {item.doc_id for item in shared_evidence}


def _entity(entity_id: str, name: str, chunk_id: str) -> Entity:
    return Entity(
        entity_id=entity_id,
        name=name,
        entity_type="CONCEPT",
        source_chunk_ids=[chunk_id],
        acl_scope=ACLScope.public(),
        ingested_at=INGESTED_AT,
        provenance=Provenance.from_document("user_docs/graph.md"),
    )


def _relation(relation_id: str, source_id: str, target_id: str, chunk_id: str) -> Relation:
    return Relation(
        relation_id=relation_id,
        source_entity_id=source_id,
        target_entity_id=target_id,
        relation_type="DESCRIBES",
        source_chunk_ids=[chunk_id],
        acl_scope=ACLScope.public(),
        ingested_at=INGESTED_AT,
        provenance=Provenance.from_document("user_docs/graph.md"),
    )


def test_graph_paths_and_evidence_do_not_leak(chunks: list[Chunk]) -> None:
    graph = FakeGraphRetriever()
    graph.index_graph(
        [
            _entity("ent_alice", "AliceSpec", "chk_alice"),
            _entity("ent_bob", "BobSpec", "chk_bob"),
            _entity("ent_shared", "SharedSpec", "chk_shared"),
            _entity("ent_public", "PublicSpec", "chk_public"),
            _entity("ent_alice_owner", "AliceOwner", "chk_alice"),
            _entity("ent_shared_owner", "SharedOwner", "chk_shared"),
        ],
        [
            _relation("rel_alice", "ent_alice_owner", "ent_alice", "chk_alice"),
            _relation("rel_bob", "ent_bob", "ent_public", "chk_bob"),
            _relation("rel_shared", "ent_shared_owner", "ent_shared", "chk_shared"),
        ],
        chunks,
    )

    assert graph.find_path("AliceOwner", "AliceSpec", filter_criteria=_filter(owner_user_id="bob")) is None
    assert graph.find_path("SharedOwner", "SharedSpec", filter_criteria=_filter()) is None

    bob_path = graph.find_path("BobSpec", "PublicSpec", filter_criteria=_filter(owner_user_id="bob"))
    assert bob_path is not None
    bob_evidence = graph.retrieve_path_evidence(
        list(bob_path), filter_criteria=_filter(owner_user_id="bob")
    )
    _assert_isolated({item.doc_id for item in bob_evidence}, "bob")

    shared_path = graph.find_path(
        "SharedOwner", "SharedSpec", filter_criteria=_filter(shared_scope=SHARED_SCOPE)
    )
    assert shared_path is not None
    shared_evidence = graph.retrieve_path_evidence(
        list(shared_path), filter_criteria=_filter(shared_scope=SHARED_SCOPE)
    )
    assert {item.doc_id for item in shared_evidence} == {SHARED_DOC}

    admin_path = graph.find_path(
        "AliceOwner", "AliceSpec", filter_criteria=_filter(is_admin=True)
    )
    assert admin_path is not None


def test_exact_cache_is_keyed_by_owner_not_shared_scope(chunks: list[Chunk]) -> None:
    cache = FakeExactCache()
    evidence = [
        Evidence(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            text=chunk.text,
            score=1.0,
            retrieval_method="hybrid",
            provenance=chunk.provenance,
        )
        for chunk in chunks
    ]
    answer = Answer(query=QUERY, answer="private", evidence=evidence)

    alice_filter = _filter(owner_user_id="alice")
    bob_filter = _filter(owner_user_id="bob")
    shared_filter = _filter(shared_scope=SHARED_SCOPE)
    other_shared_filter = _filter(shared_scope="other-team")

    cache.set(
        QUERY,
        answer,
        ACLScope.owner("alice"),
        owner_user_id=alice_filter.owner_user_id,
    )
    cache.set(
        "shared " + QUERY,
        answer,
        ACLScope.shared(SHARED_SCOPE),
        owner_user_id=shared_filter.owner_user_id,
    )

    assert cache.get(QUERY, ACLScope.owner("alice"), owner_user_id="alice") is not None
    assert cache.get(QUERY, ACLScope.public(), owner_user_id="bob") is None
    # The exact cache contract is owner-scoped only; shared scope is metadata
    # for invalidation, not a key input. Real callers always pass owner_user_id.
    assert cache.get("shared " + QUERY, ACLScope.shared(SHARED_SCOPE)) is not None
    assert cache.get("shared " + QUERY, ACLScope.shared("other-team")) is not None
    assert other_shared_filter.acl_scope.shared_scope == "other-team"

    assert cache.invalidate_owner("alice") == 1
    assert cache.invalidate_shared_scope(SHARED_SCOPE) == 1
    assert cache.stats["entries"] == 0


def _dev_user_filter(username: str, shared_scope: str | None = None) -> RetrievalFilter:
    user = AuthenticatedUser(
        username,
        {"user_id": username, "name": username.title(), "shared_scopes": []},
    )
    return user.to_retrieval_filter(shared_scope)


@pytest.mark.asyncio
async def test_orchestrator_end_to_end_does_not_leak(chunks: list[Chunk]) -> None:
    orchestrator, _ = build_hermetic_orchestrator(chunks)
    alice = _dev_user_filter("alice")
    bob = _dev_user_filter("bob")

    alice_state = await orchestrator.run(
        query=QUERY,
        acl_scope=alice.acl_scope,
        owner_user_id=alice.owner_user_id,
        is_admin=alice.is_admin,
        retrieval_only=True,
        retrieval_config="hybrid",
    )
    assert {item.doc_id for item in alice_state.get("evidence", [])} == {
        ALICE_PRIVATE_DOC,
        PUBLIC_DOC,
    }

    bob_state = await orchestrator.run(
        query=QUERY,
        acl_scope=bob.acl_scope,
        owner_user_id=bob.owner_user_id,
        is_admin=bob.is_admin,
        retrieval_only=True,
        retrieval_config="hybrid",
    )
    bob_docs = {item.doc_id for item in bob_state.get("evidence", [])}
    _assert_isolated(bob_docs, "bob")
    assert BOB_PRIVATE_DOC in bob_docs
    assert PUBLIC_DOC in bob_docs
    assert not bob_state.get("is_cached", False)

    shared_state = await orchestrator.run(
        query=QUERY,
        acl_scope=ACLScope.shared(SHARED_SCOPE),
        retrieval_only=True,
        retrieval_config="hybrid",
    )
    assert SHARED_DOC in {item.doc_id for item in shared_state.get("evidence", [])}
