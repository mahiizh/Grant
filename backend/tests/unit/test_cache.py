from app.cache import (
    CacheInvalidator,
    ExactCache,
    SemanticCache,
    generate_exact_cache_key,
    validate_cache_hit,
)
from app.core.acl import ACLScope
from app.domain import Answer, Evidence, Provenance


def create_sample_answer(query: str, text: str) -> Answer:
    prov = Provenance.from_document("corpus/rfc_001.md")
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
    acl_public = ACLScope.public(tenant_id="tenant_1")
    acl_restricted = ACLScope.restricted(allowed_roles={"admin"}, tenant_id="tenant_1")

    key1 = generate_exact_cache_key("Which database is source of truth?", acl_public)
    key2 = generate_exact_cache_key("  which database is SOURCE of truth?  ", acl_public)
    assert key1 == key2  # Normalization works

    key_diff_acl = generate_exact_cache_key("Which database is source of truth?", acl_restricted)
    assert key1 != key_diff_acl  # Security isolation works


def test_exact_cache_hit_and_metrics() -> None:
    cache = ExactCache()
    cache.clear()
    acl = ACLScope.public()
    query = "What database is used for vectors?"
    ans = create_sample_answer(query, "Qdrant is used for vectors.")

    # Miss on cold cache
    assert cache.get(query, acl) is None
    assert cache.stats["misses"] == 1

    # Store in cache
    cache.set(query, ans, acl)
    assert cache.stats["entries"] == 1

    # Hit on warm cache
    hit = cache.get(query, acl)
    assert hit is not None
    assert hit.answer == "Qdrant is used for vectors."
    assert hit.router_strategy == "cache"
    assert hit.latency_ms < 2.0  # Ultra-fast cached response
    assert cache.stats["hits"] == 1


def test_exact_cache_tenant_isolation() -> None:
    cache = ExactCache()
    acl_a = ACLScope.public(tenant_id="tenant_a")
    acl_b = ACLScope.public(tenant_id="tenant_b")

    query = "Who leads SRE?"
    ans = create_sample_answer(query, "Bob Kumar leads SRE.")

    cache.set(query, ans, acl_a)

    # Tenant A hits
    assert cache.get(query, acl_a) is not None

    # Tenant B misses (data isolation guaranteed)
    assert cache.get(query, acl_b) is None


def test_semantic_cache_paraphrase_hit() -> None:
    sem_cache = SemanticCache(similarity_threshold=0.75)
    sem_cache.clear()
    acl = ACLScope.public()

    q1 = "Which system is the single source of truth for ingested docs?"
    q2 = "Which system is the single source of truth for all documents?"
    ans = create_sample_answer(q1, "PostgreSQL 16 acts as single source of truth.")

    sem_cache.set(q1, ans, acl)

    # Q2 is a paraphrase of Q1
    hit = sem_cache.get(q2, acl)
    assert hit is not None
    assert hit.answer == ans.answer
    assert hit.router_strategy == "semantic_cache"
    assert hit.latency_ms < 10.0


def test_semantic_cache_guardrails_prevent_wrong_hits() -> None:
    sem_cache = SemanticCache(similarity_threshold=0.75)
    sem_cache.clear()
    acl = ACLScope.public()

    # Cached incident query
    q_cached = "What was the failure rate during incident INC-2026-04?"
    ans = create_sample_answer(q_cached, "Customers experienced a 24% failure rate.")
    sem_cache.set(q_cached, ans, acl)

    # Near-miss query with DIFFERENT incident number: INC-2026-05
    q_near_miss = "What was the failure rate during incident INC-2026-05?"

    # Raw guardrail check detects code mismatch
    guard_res = validate_cache_hit(q_near_miss, q_cached)
    assert not guard_res.passed
    assert "inc-2026-05" in guard_res.reason

    # Semantic cache blocks the hit due to guardrails!
    hit = sem_cache.get(q_near_miss, acl)
    assert hit is None
    assert sem_cache.stats["guard_rejections"] == 1


def test_outbox_cache_invalidation_lifecycle() -> None:
    exact = ExactCache()
    exact.clear()
    sem = SemanticCache()
    sem.clear()
    invalidator = CacheInvalidator(exact_cache=exact, semantic_cache=sem, initial_index_version=1)

    acl = ACLScope.public(tenant_id="tenant_1")
    query = "What is the reconciler schedule?"
    ans = create_sample_answer(query, "02:00 UTC")

    exact.set(query, ans, acl, index_version=1)
    sem.set(query, ans, acl, index_version=1)

    assert exact.get(query, acl, index_version=1) is not None
    assert sem.get(query, acl, index_version=1) is not None

    # Handle outbox invalidation event (e.g. document update or deletion)
    invalidator.handle_outbox_event(
        event_type="CACHE_INVALIDATED",
        payload={"tenant_id": "tenant_1"},
    )

    # New index version is 2
    assert invalidator.current_index_version == 2

    # Query with new index version misses old cache
    assert exact.get(query, acl, index_version=2) is None
    assert sem.get(query, acl, index_version=2) is None
