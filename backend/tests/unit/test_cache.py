import hashlib
import json
from typing import Any, cast

from app.cache import CacheInvalidator, ExactCache, generate_exact_cache_key
from app.cache.exact import DOCS_CACHE_TTL_SECONDS, WEB_CACHE_TTL_SECONDS
from app.cache.keys import DEFAULT_INDEX_VERSION
from app.core.acl import ACLScope
from app.domain import Answer, Evidence, Provenance
from tests.fakes.fake_redis import FakeRedis


def _fake_exact_cache(**kwargs: Any) -> ExactCache:
    """Return an ExactCache backed by FakeRedis so unit tests never need a live Redis."""
    return ExactCache(redis_client=cast(Any, FakeRedis()), **kwargs)


def create_sample_answer(query: str, text: str, source_kind: str = "docs") -> Answer:
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
        source_kind=source_kind,  # type: ignore[arg-type]
    )


def test_exact_cache_key_generation() -> None:
    public = ACLScope.public()
    query = "Which database is source of truth?"
    expected = hashlib.sha256(
        "|".join(
            (
                "anon",
                str(DEFAULT_INDEX_VERSION),
                "v1",
                "grounded_only",
                "which database is source of truth?",
            )
        ).encode("utf-8")
    ).hexdigest()

    assert generate_exact_cache_key(query, public) == expected
    assert generate_exact_cache_key(
        "  which database is SOURCE of truth?  ", public
    ) == expected


def test_exact_key_uses_only_documented_inputs() -> None:
    query = "What is the oncall policy?"
    alice = ACLScope.owner("usr_alice_01")
    shared = ACLScope.shared("team_a")

    base = generate_exact_cache_key(query, alice, owner_user_id="usr_alice_01")
    assert base == generate_exact_cache_key("  WHAT is the oncall POLICY? ", shared, owner_user_id="usr_alice_01")
    assert base != generate_exact_cache_key(query, alice, owner_user_id="usr_bob_02")
    assert base != generate_exact_cache_key(
        query, alice, owner_user_id="usr_alice_01", index_version=DEFAULT_INDEX_VERSION + 1
    )
    assert base != generate_exact_cache_key(
        query, alice, owner_user_id="usr_alice_01", prompt_version="v2"
    )
    assert base != generate_exact_cache_key(
        query,
        alice,
        owner_user_id="usr_alice_01",
        answer_policy="grounded_plus_web",
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


def test_exact_cache_owner_isolation() -> None:
    cache = _fake_exact_cache()
    query = "Who leads SRE?"
    ans = create_sample_answer(query, "Alice leads SRE.")

    cache.set(query, ans, ACLScope.owner("usr_alice_01"), owner_user_id="usr_alice_01")
    assert cache.get(query, ACLScope.owner("usr_alice_01"), owner_user_id="usr_alice_01") is not None
    assert cache.get(query, ACLScope.owner("usr_bob_02"), owner_user_id="usr_bob_02") is None
    assert cache.get(query, ACLScope.public()) is None


def test_exact_cache_ttls_are_24h_docs_and_6h_web() -> None:
    redis = FakeRedis()
    cache = ExactCache(redis_client=cast(Any, redis))
    query = "What is the current population of Tokyo?"
    docs_key = cache.set(
        "Where is the evidence stored?",
        create_sample_answer(query, "PostgreSQL."),
        ACLScope.public(),
    )
    web_key = cache.set(
        query,
        create_sample_answer(query, "Tokyo has 14 million residents.", source_kind="web"),
        ACLScope.public(),
    )

    assert redis.ttls[f"exact:{docs_key}"] == DOCS_CACHE_TTL_SECONDS
    assert redis.ttls[f"exact:{web_key}"] == WEB_CACHE_TTL_SECONDS
    assert DOCS_CACHE_TTL_SECONDS == 86400
    assert WEB_CACHE_TTL_SECONDS == 21600


def test_outbox_cache_invalidation_lifecycle() -> None:
    cache = _fake_exact_cache()
    cache.clear()
    invalidator = CacheInvalidator(exact_cache=cache)

    acl = ACLScope.owner("usr_alice_01")
    query = "What is the reconciler schedule?"
    ans = create_sample_answer(query, "02:00 UTC")
    cache.set(query, ans, acl, owner_user_id="usr_alice_01")

    assert cache.get(query, acl, owner_user_id="usr_alice_01") is not None
    invalidator.handle_outbox_event(
        event_type="CACHE_INVALIDATED",
        payload={"owner_user_id": "usr_alice_01"},
    )
    version = cache.current_index_version("usr_alice_01")
    assert version == DEFAULT_INDEX_VERSION + 1
    assert cache.get(
        query, acl, index_version=version, owner_user_id="usr_alice_01"
    ) is None


def test_upload_version_bump_turns_repeat_hit_into_miss() -> None:
    redis = FakeRedis()
    cache = ExactCache(redis_client=cast(Any, redis))
    invalidator = CacheInvalidator(exact_cache=cache)
    acl = ACLScope.owner("usr_alice_01")
    query = "Which controls does ISO 27001 require?"
    ans = create_sample_answer(query, "Access control and incident response.")

    cache.set(query, ans, acl, owner_user_id="usr_alice_01")
    assert cache.get(query, acl, owner_user_id="usr_alice_01") is not None

    # The worker stages CACHE_INVALIDATED after an upload is indexed.
    invalidator.handle_outbox_event(
        event_type="CACHE_INVALIDATED",
        payload={"owner_user_id": "usr_alice_01", "reason": "document_indexed"},
    )
    version = cache.current_index_version("usr_alice_01")
    assert cache.get(query, acl, index_version=version, owner_user_id="usr_alice_01") is None

    cache.set(query, ans, acl, index_version=version, owner_user_id="usr_alice_01")
    assert cache.get(query, acl, index_version=version, owner_user_id="usr_alice_01") is not None


def test_version_bump_is_owner_scoped() -> None:
    redis = FakeRedis()
    invalidator = CacheInvalidator(redis_client=cast(Any, redis))

    assert invalidator.increment_owner_index_version("usr_alice_01") == 1
    assert invalidator.increment_owner_index_version("usr_alice_01") == 2
    assert invalidator.current_owner_index_version("usr_bob_02") == DEFAULT_INDEX_VERSION
    assert invalidator.current_owner_index_version("usr_alice_01") == 2


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

    assert summary["new_index_version"] == DEFAULT_INDEX_VERSION + 1
    assert summary["redis_keys_purged"] == 1
    assert "exact:cache:exact:v1:v1:acl:q" not in redis.store
    assert "exact:cache:exact:v1:v1:acl:q2" in redis.store
