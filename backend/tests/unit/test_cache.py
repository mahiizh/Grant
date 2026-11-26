import json
from typing import Any, cast

from app.cache import CacheInvalidator, ExactCache, generate_exact_cache_key
from app.core.acl import ACLScope
from app.domain import Answer, Evidence, Provenance
from tests.fakes.fake_redis import FakeRedis


def _fake_exact_cache(**kwargs: Any) -> ExactCache:
    """Return an ExactCache backed by FakeRedis so unit tests never need a live Redis."""
    return ExactCache(redis_client=cast(Any, FakeRedis()), **kwargs)


def create_sample_answer(query: str, text: str) -> Answer:
    prov = Provenance.from_document("user_docs/rfc_001.md")
    ev = Evidence(
        chunk_id="chunk_01",
        doc_id="doc_01",
        text=text,
        score=0.95,
        retrieval_method="hybrid",
        provenance=prov,
    )
    return Answer(
        query=query,
        answer=text,
        evidence=[ev],
        router_strategy="hybrid",
        cost_usd=0.002,
        latency_ms=450.0,
    )


def test_exact_cache_key_generation() -> None:
    public = ACLScope.public()
    alice = ACLScope.owner("alice")
    shared = ACLScope.shared("team_a")

    key1 = generate_exact_cache_key("Which database is source of truth?", public)
    key2 = generate_exact_cache_key("  which database is SOURCE of truth?  ", public)
    assert key1 == key2  # Normalization works

    assert key1 != generate_exact_cache_key("Which database is source of truth?", alice)
    assert key1 != generate_exact_cache_key("Which database is source of truth?", shared)
    assert generate_exact_cache_key("q", alice, owner_user_id="alice") != generate_exact_cache_key(
        "q", alice, owner_user_id="bob"
    )


def test_exact_cache_hit_and_metrics() -> None:
    cache = _fake_exact_cache()
    cache.clear()
    acl = ACLScope.public()
    query = "What database is used for vectors?"
    ans = create_sample_answer(query, "Qdrant is used for vectors.")

    assert cache.get(query, acl) is None
    assert cache.stats["misses"] == 1

    cache.set(query, ans, acl)
    assert cache.stats["entries"] == 1

    hit = cache.get(query, acl)
    assert hit is not None
    assert hit.answer == "Qdrant is used for vectors."
    assert hit.router_strategy == "cache"
    assert hit.latency_ms < 2.0
    assert cache.stats["hits"] == 1


def test_exact_cache_scope_isolation() -> None:
    cache = _fake_exact_cache()
    query = "Who leads SRE?"
    ans = create_sample_answer(query, "Alice leads SRE.")

    cache.set(query, ans, ACLScope.owner("alice"), owner_user_id="alice")
    assert cache.get(query, ACLScope.owner("alice"), owner_user_id="alice") is not None
    assert cache.get(query, ACLScope.owner("bob"), owner_user_id="bob") is None
    assert cache.get(query, ACLScope.public()) is None

    shared_query = "What is the oncall policy?"
    cache.set(shared_query, ans, ACLScope.shared("team_a"))
    assert cache.get(shared_query, ACLScope.shared("team_a")) is not None
    assert cache.get(shared_query, ACLScope.shared("team_b")) is None


def test_outbox_cache_invalidation_lifecycle() -> None:
    cache = _fake_exact_cache()
    cache.clear()
    invalidator = CacheInvalidator(exact_cache=cache, initial_index_version=1)

    acl = ACLScope.owner("alice")
    query = "What is the reconciler schedule?"
    ans = create_sample_answer(query, "02:00 UTC")
    cache.set(query, ans, acl, index_version=1, owner_user_id="alice")

    assert cache.get(query, acl, index_version=1, owner_user_id="alice") is not None
    invalidator.handle_outbox_event(
        event_type="CACHE_INVALIDATED",
        payload={"owner_user_id": "alice"},
    )
    assert invalidator.current_index_version == 2
    assert cache.get(query, acl, index_version=2, owner_user_id="alice") is None


def test_exact_cache_invalidate_document() -> None:
    cache = ExactCache(redis_client=cast(Any, FakeRedis()))
    acl = ACLScope.public()
    query = "What is the reconciler schedule?"
    ans = create_sample_answer(query, "02:00 UTC")

    cache.set(query, ans, acl)
    assert cache.get(query, acl) is not None

    purged = cache.invalidate_document("doc_01")
    assert purged == 1
    assert cache.get(query, acl) is None


def test_cache_invalidator_purges_exact_document_keys() -> None:
    redis = FakeRedis()
    exact_payload = {
        "query": "q",
        "answer": "a",
        "evidence": [{"doc_id": "doc_01", "chunk_id": "chk_01"}],
    }
    other_payload = {
        "query": "q2",
        "answer": "a2",
        "evidence": [{"doc_id": "doc_02", "chunk_id": "chk_02"}],
    }
    redis.seed("exact:cache:exact:v1:v1:acl:q", json.dumps(exact_payload))
    redis.seed("exact:cache:exact:v1:v1:acl:q2", json.dumps(other_payload))

    invalidator = CacheInvalidator(redis_client=cast(Any, redis))
    summary = invalidator.handle_outbox_event(
        event_type="CACHE_INVALIDATED",
        payload={"doc_id": "doc_01", "reason": "document_deletion"},
    )

    assert summary["new_index_version"] == 2
    assert summary["redis_keys_purged"] == 1
    assert "exact:cache:exact:v1:v1:acl:q" not in redis.store
    assert "exact:cache:exact:v1:v1:acl:q2" in redis.store
