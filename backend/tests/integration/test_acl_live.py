"""Live-container ACL leak tests for Qdrant, Neo4j, and HTTP surfaces.

These tests create their own caller-owned documents in the isolated test stores;
they never depend on a bundled demo corpus or on the developer's dev database.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.acl import ACLScope
from app.core.auth import AuthenticatedUser
from app.core.config import get_settings
from app.db.models import DocumentRecord
from app.db.postgres import DocumentRepository, get_session, init_db
from app.domain.ids import generate_doc_id
from app.graph.retrievers import GraphRetriever
from app.indexing.neo4j_indexer import Neo4jIndexer
from app.indexing.outbox_worker import OutboxWorker
from app.ingestion.pipeline import IngestionPipeline
from app.main import app
from app.retrieval.dense import DenseRetriever
from app.retrieval.filters import RetrievalFilter
from app.retrieval.reranker import get_reranker
from app.retrieval.sparse import BM25Retriever

PRIVATE_SOURCE = "live_acl_private"
SHARED_SOURCE = "live_acl_shared"
PRIVATE_DOC_ID = generate_doc_id(PRIVATE_SOURCE)
SHARED_DOC_ID = generate_doc_id(SHARED_SOURCE)
PRIVATE_TITLE = "Alice Private Ledger"
SHARED_TITLE = "Analytics Runbook"
QUERY = "PostgreSQL outbox ledger"

PRIVATE_ENTITY_ID = "ent_live_acl_private"
SHARED_ENTITY_ID = "ent_live_acl_shared"
PUBLIC_ENTITY_ID = "ent_live_acl_public"
ENTITY_IDS = [PRIVATE_ENTITY_ID, SHARED_ENTITY_ID, PUBLIC_ENTITY_ID]

PRIVATE_CONTENT = f"""# {PRIVATE_TITLE}
**Document ID**: `{PRIVATE_DOC_ID}`

Zara Okafor owns the private ledger. OutboxWorker syncs PostgreSQL for Alice Chen.
"""

SHARED_CONTENT = f"""# {SHARED_TITLE}
**Document ID**: `{SHARED_DOC_ID}`

The analytics runbook uses PostgreSQL and Redis. Zara Okafor reviews it.
"""


class _FakeReranker:
    """Constant scorer so compare tests exercise ACL plumbing, not the model."""

    def predict_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [1.0 for _ in pairs]


def _filter(username: str, scope: str | None = None) -> RetrievalFilter:
    user = AuthenticatedUser(username, get_settings().DEV_USERS[username])
    return user.to_retrieval_filter(scope)


async def _drain_outbox() -> int:
    worker = OutboxWorker()
    try:
        return await worker.drain()
    finally:
        await worker.qdrant.close()
        await worker.neo4j.close()
        await worker.entity_indexer.close()


async def _delete_documents(doc_ids: list[str]) -> None:
    async with get_session() as session:
        rows = (
            (
                await session.execute(
                    select(DocumentRecord).where(DocumentRecord.doc_id.in_(doc_ids))
                )
            )
            .scalars()
            .all()
        )
        for doc in rows:
            await DocumentRepository.delete_document(session, doc.doc_id)
        await session.commit()
    await _drain_outbox()


async def _seed_graph() -> None:
    neo = Neo4jIndexer()
    try:
        await neo.merge_node(
            entity_id=PRIVATE_ENTITY_ID,
            name="Zara Okafor",
            entity_type="Person",
            acl_scope=ACLScope.owner("usr_alice_01").model_dump(mode="json"),
            properties={"doc_id": PRIVATE_DOC_ID, "source_kind": "document"},
        )
        await neo.merge_node(
            entity_id=SHARED_ENTITY_ID,
            name="Analytics Beacon",
            entity_type="Concept",
            acl_scope=ACLScope.shared("shared-analytics").model_dump(mode="json"),
            properties={"doc_id": SHARED_DOC_ID, "source_kind": "document"},
        )
        await neo.merge_node(
            entity_id=PUBLIC_ENTITY_ID,
            name="Public Beacon",
            entity_type="Concept",
            acl_scope=ACLScope.public().model_dump(mode="json"),
            properties={"doc_id": "", "source_kind": "document"},
        )
        await neo.merge_edge(
            PRIVATE_ENTITY_ID,
            SHARED_ENTITY_ID,
            "RELATES_TO",
            acl_scope=ACLScope.owner("usr_alice_01").model_dump(mode="json"),
        )
        await neo.merge_edge(
            PUBLIC_ENTITY_ID,
            PRIVATE_ENTITY_ID,
            "RELATES_TO",
            acl_scope=ACLScope.public().model_dump(mode="json"),
        )
    finally:
        await neo.close()


async def _clear_graph() -> None:
    neo = Neo4jIndexer()
    try:
        async with neo.driver.session(database=neo.database) as session:
            await session.run(
                "MATCH (n:Entity) WHERE n.id IN $ids DETACH DELETE n",
                ids=ENTITY_IDS,
            )
    finally:
        await neo.close()


@pytest_asyncio.fixture
async def acl_corpus() -> AsyncGenerator[dict[str, str], None]:
    """Install a private, a shared, and a public fixture in the test stores."""
    await init_db()
    doc_ids = [PRIVATE_DOC_ID, SHARED_DOC_ID]
    await _delete_documents(doc_ids)
    await _clear_graph()

    async with get_session() as session:
        await IngestionPipeline.ingest_text(
            session=session,
            content=PRIVATE_CONTENT,
            source_uri=PRIVATE_SOURCE,
            acl_scope=ACLScope.owner("usr_alice_01"),
            owner_user_id="usr_alice_01",
        )
        await IngestionPipeline.ingest_text(
            session=session,
            content=SHARED_CONTENT,
            source_uri=SHARED_SOURCE,
            acl_scope=ACLScope.shared("shared-analytics"),
            owner_user_id="usr_alice_01",
        )
    await _drain_outbox()
    await _seed_graph()

    yield {"private": PRIVATE_DOC_ID, "shared": SHARED_DOC_ID}

    await _delete_documents(doc_ids)
    await _clear_graph()


def _assert_private_doc_hidden(doc_ids: set[str]) -> None:
    assert PRIVATE_DOC_ID not in doc_ids, "ACL leak: Alice's private chunk was retrieved"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qdrant_payload_filter_does_not_leak(acl_corpus: dict[str, str]) -> None:
    """Qdrant dense and sparse search must hide Alice's private chunks from Bob."""
    bob = _filter("bob")
    alice = _filter("alice")

    for retriever in (DenseRetriever(), BM25Retriever()):
        bob_docs = {
            payload["doc_id"]
            for _, _, payload in await retriever.search(QUERY, top_k=45, filter_criteria=bob)
        }
        _assert_private_doc_hidden(bob_docs)

        alice_docs = {
            payload["doc_id"]
            for _, _, payload in await retriever.search(QUERY, top_k=45, filter_criteria=alice)
        }
        # Non-vacuity: Alice's filter really does admit her own private document.
        assert PRIVATE_DOC_ID in alice_docs


@pytest.mark.integration
@pytest.mark.asyncio
async def test_neo4j_cypher_acl_does_not_leak(acl_corpus: dict[str, str]) -> None:
    """Cypher predicates must hide owner-private nodes and paths from other users."""
    graph = GraphRetriever()
    try:
        bob = _filter("bob")
        alice = _filter("alice")
        alice_shared = _filter("alice", "shared-analytics")

        bob_entities = await graph.search_entities("Zara Okafor", filter_criteria=bob)
        assert bob_entities == []

        alice_entities = await graph.search_entities("Zara Okafor", filter_criteria=alice)
        assert any(e["id"] == PRIVATE_ENTITY_ID for e in alice_entities)

        # Shared nodes become visible only when the caller requests that scope.
        assert await graph.search_entities("Analytics Beacon", filter_criteria=alice) == []
        assert any(
            e["id"] == SHARED_ENTITY_ID
            for e in await graph.search_entities(
                "Analytics Beacon", filter_criteria=alice_shared
            )
        )

        assert (
            await graph.find_path("Public Beacon", "Zara Okafor", filter_criteria=bob) is None
        )
        assert (
            await graph.find_path(
                "Zara Okafor", "Analytics Beacon", filter_criteria=alice_shared
            )
            is not None
        )

        bob_evidence = await graph.retrieve_path_evidence(
            [PUBLIC_ENTITY_ID], filter_criteria=bob
        )
        _assert_private_doc_hidden({item.doc_id for item in bob_evidence})
    finally:
        await graph.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retrieval_compare_endpoint_does_not_leak(acl_corpus: dict[str, str]) -> None:
    """`/retrieval/compare` must apply the same owner/shared ACL to every branch."""
    app.dependency_overrides[get_reranker] = _FakeReranker
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            forbidden = await client.get(
                "/api/v1/retrieval/compare",
                params={"query": QUERY, "scope": "shared-analytics"},
                headers={"X-Dev-User": "bob"},
            )
            assert forbidden.status_code == 403

            bob_resp = await client.get(
                "/api/v1/retrieval/compare",
                params={"query": QUERY},
                headers={"X-Dev-User": "bob"},
            )
            assert bob_resp.status_code == 200
            bob_doc_ids = {c["doc_title"] for c in bob_resp.json()["candidates"]}
            assert PRIVATE_DOC_ID not in bob_doc_ids

            alice_resp = await client.get(
                "/api/v1/retrieval/compare",
                params={"query": QUERY},
                headers={"X-Dev-User": "alice"},
            )
            assert alice_resp.status_code == 200
            alice_doc_ids = {c["doc_title"] for c in alice_resp.json()["candidates"]}
            assert PRIVATE_DOC_ID in alice_doc_ids
    finally:
        app.dependency_overrides.pop(get_reranker, None)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_graph_endpoints_do_not_leak(acl_corpus: dict[str, str]) -> None:
    """`/graph` and `/graph/path` must not expose owner-private nodes to Bob."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        bob_resp = await client.get("/api/v1/graph", headers={"X-Dev-User": "bob"})
        assert bob_resp.status_code == 200
        bob_names: list[dict[str, Any]] = bob_resp.json()["nodes"]
        bob_names = {node["name"] for node in bob_names}
        assert "Zara Okafor" not in bob_names
        assert "Analytics Beacon" not in bob_names
        # Non-vacuity: Bob still sees the public subgraph.
        assert "Public Beacon" in bob_names

        alice_resp = await client.get(
            "/api/v1/graph",
            params={"scope": "shared-analytics"},
            headers={"X-Dev-User": "alice"},
        )
        assert alice_resp.status_code == 200
        alice_names = {node["name"] for node in alice_resp.json()["nodes"]}
        assert "Zara Okafor" in alice_names
        assert "Analytics Beacon" in alice_names

        bob_path = await client.get(
            "/api/v1/graph/path",
            params={"from": "Public Beacon", "to": "Zara Okafor"},
            headers={"X-Dev-User": "bob"},
        )
        assert bob_path.status_code == 200
        assert bob_path.json()["found"] is False

        alice_path = await client.get(
            "/api/v1/graph/path",
            params={
                "from": "Zara Okafor",
                "to": "Analytics Beacon",
                "scope": "shared-analytics",
            },
            headers={"X-Dev-User": "alice"},
        )
        assert alice_path.status_code == 200
        assert alice_path.json()["found"] is True
