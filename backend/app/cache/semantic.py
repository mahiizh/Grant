import json
import logging
from dataclasses import dataclass

import redis

from app.cache.guards import validate_cache_hit
from app.cache.keys import generate_semantic_cache_key
from app.core.acl import ACLScope
from app.core.config import get_settings
from app.domain import Answer, Evidence, Provenance, SourceTier
from app.retrieval.dense import cosine_similarity
from app.retrieval.embeddings import get_embedding_service

logger = logging.getLogger(__name__)


@dataclass
class SemanticCacheEntry:
    query: str
    embedding: list[float]
    answer: Answer
    acl_scope: ACLScope
    index_version: int
    tenant_id: str
    prompt_version: str = "v1"
    as_of: str | None = None
    owner_user_id: str | None = None


class SemanticCache:
    """Production Semantic Cache combining Redis persistence and FastEmbed similarity."""

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        redis_client: redis.Redis | None = None,
        enabled: bool = True,
    ) -> None:
        self.threshold = similarity_threshold
        settings = get_settings()
        self.enabled = enabled
        self._hits = 0
        self._misses = 0
        self._guard_rejections = 0
        self._entries: list[SemanticCacheEntry] = []
        self.client: redis.Redis | None = None
        self.embedding_service = get_embedding_service()
        if not self.enabled:
            return

        try:
            self.client = redis_client or redis.Redis.from_url(settings.redis_url)
            self._load_from_redis()
        except Exception as e:
            logger.warning("Failed connecting to Redis for SemanticCache: %s", e)
            self.client = None

    def _load_from_redis(self) -> None:
        """Load semantic cache entries from Redis."""
        if not self.client:
            return
        try:
            for k in self.client.scan_iter("sem:*"):
                raw = self.client.get(k)
                if not raw:
                    continue
                raw_str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                data = json.loads(raw_str)
                acl_data = data.get("acl_scope", {})
                scope = ACLScope(
                    tenant_id=acl_data.get("tenant_id", "default"),
                    allowed_roles=frozenset(acl_data.get("allowed_roles", [])),
                    allowed_groups=frozenset(acl_data.get("allowed_groups", [])),
                    is_public=acl_data.get("is_public", True),
                )
                evidence_items = []
                for ev in data.get("evidence", []):
                    prov = Provenance(
                        tier=SourceTier(ev.get("tier", 1)),
                        source_uri=ev.get("source_uri", ""),
                        confidence=1.0,
                        verified=True,
                    )
                    method = ev.get("retrieval_method", "hybrid")
                    if method not in ("dense", "sparse", "graph", "hybrid", "rerank", "web"):
                        method = "hybrid"
                    evidence_items.append(
                        Evidence(
                            chunk_id=ev["chunk_id"],
                            doc_id=ev["doc_id"],
                            text=ev["text"],
                            score=ev.get("score", 1.0),
                            retrieval_method=method,
                            provenance=prov,
                        )
                    )
                ans = Answer(
                    query=data["query"],
                    answer=data["answer"],
                    evidence=evidence_items,
                    is_abstention=data.get("is_abstention", False),
                    router_strategy="semantic_cache",
                    cost_usd=0.0,
                    latency_ms=2.5,
                    source_kind=data.get("source_kind", "docs"),
                    web_sources=list(data.get("web_sources", []) or []),
                )
                self._entries.append(
                    SemanticCacheEntry(
                        query=data["query"],
                        embedding=data["embedding"],
                        answer=ans,
                        acl_scope=scope,
                        index_version=data.get("index_version", 1),
                        tenant_id=scope.tenant_id,
                        prompt_version=data.get("prompt_version", "v1"),
                        as_of=data.get("as_of"),
                        owner_user_id=data.get("owner_user_id"),
                    )
                )
        except Exception as e:
            logger.error("Failed loading semantic entries from Redis: %s", e)

    def get(
        self,
        query: str,
        acl_scope: ACLScope,
        index_version: int = 1,
        prompt_version: str = "v1",
        as_of: str | None = None,
        owner_user_id: str | None = None,
    ) -> Answer | None:
        """Search for a semantically similar query, verified by entity/number guardrails."""
        if not self.enabled:
            self._misses += 1
            return None
        if not self._entries:
            self._misses += 1
            return None

        query_vec = self.embedding_service.embed_query_dense(query)
        candidates: list[tuple[float, SemanticCacheEntry]] = []

        for entry in self._entries:
            if owner_user_id is not None and entry.owner_user_id != owner_user_id:
                continue
            if entry.tenant_id != acl_scope.tenant_id or entry.index_version != index_version:
                continue
            if entry.prompt_version != prompt_version or entry.as_of != as_of:
                continue

            if not entry.acl_scope.permits(
                user_roles=acl_scope.allowed_roles,
                user_groups=acl_scope.allowed_groups,
                tenant_id=acl_scope.tenant_id,
            ):
                continue

            sim = cosine_similarity(query_vec, entry.embedding)
            if sim >= self.threshold:
                candidates.append((sim, entry))

        if not candidates:
            self._misses += 1
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)

        for _sim, candidate in candidates:
            guard_result = validate_cache_hit(
                new_query=query,
                cached_query=candidate.query,
            )

            if not guard_result.passed:
                self._guard_rejections += 1
                continue

            self._hits += 1
            return Answer(
                query=query,
                answer=candidate.answer.answer,
                evidence=candidate.answer.evidence,
                is_abstention=candidate.answer.is_abstention,
                router_strategy="semantic_cache",
                cost_usd=0.0,
                latency_ms=3.5,
            )

        self._misses += 1
        return None

    def set(
        self,
        query: str,
        answer: Answer,
        acl_scope: ACLScope,
        index_version: int = 1,
        ttl_seconds: int = 3600,
        prompt_version: str = "v1",
        as_of: str | None = None,
        owner_user_id: str | None = None,
    ) -> None:
        """Store query embedding and answer in the semantic cache and Redis."""
        if not self.enabled:
            return
        query_vec = self.embedding_service.embed_query_dense(query)
        entry = SemanticCacheEntry(
            query=query,
            embedding=query_vec,
            answer=answer,
            acl_scope=acl_scope,
            index_version=index_version,
            tenant_id=acl_scope.tenant_id,
            prompt_version=prompt_version,
            as_of=as_of,
            owner_user_id=owner_user_id,
        )
        self._entries.append(entry)

        if self.client:
            try:
                payload = {
                    "query": query,
                    "embedding": query_vec,
                    "answer": answer.answer,
                    "is_abstention": answer.is_abstention,
                    "source_kind": answer.source_kind,
                    "web_sources": list(answer.web_sources or []),
                    "index_version": index_version,
                    "prompt_version": prompt_version,
                    "as_of": as_of,
                    "owner_user_id": owner_user_id,
                    "acl_scope": {
                        "tenant_id": acl_scope.tenant_id,
                        "allowed_roles": list(acl_scope.allowed_roles),
                        "allowed_groups": list(acl_scope.allowed_groups),
                        "is_public": acl_scope.is_public,
                    },
                    "evidence": [
                        {
                            "chunk_id": ev.chunk_id,
                            "doc_id": ev.doc_id,
                            "text": ev.text,
                            "score": ev.score,
                            "tier": int(ev.provenance.tier),
                            "source_uri": ev.provenance.source_uri,
                        }
                        for ev in answer.evidence
                    ],
                }
                k = generate_semantic_cache_key(
                    query=query,
                    acl_scope=acl_scope,
                    index_version=index_version,
                    prompt_version=prompt_version,
                    as_of=as_of,
                    owner_user_id=owner_user_id,
                )
                self.client.set(k, json.dumps(payload), ex=ttl_seconds)
            except Exception as e:
                logger.error("Failed saving semantic entry to Redis: %s", e)

    def invalidate_by_version(self, min_version: int) -> int:
        """Purge entries whose index_version < min_version."""
        if not self.enabled:
            return 0
        initial_len = len(self._entries)
        self._entries = [e for e in self._entries if e.index_version >= min_version]
        return initial_len - len(self._entries)

    def invalidate_document(self, doc_id: str) -> int:
        """Purge entries whose evidence cites ``doc_id`` from memory and Redis."""
        if not self.enabled:
            return 0
        initial_len = len(self._entries)
        self._entries = [
            entry
            for entry in self._entries
            if not any(ev.doc_id == doc_id for ev in entry.answer.evidence)
        ]
        purged = initial_len - len(self._entries)

        if self.client:
            try:
                for k in self.client.scan_iter("sem:*"):
                    raw = self.client.get(k)
                    if not raw:
                        continue
                    raw_str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                    data = json.loads(raw_str)
                    evidence = data.get("evidence", [])
                    if any(ev.get("doc_id") == doc_id for ev in evidence):
                        self.client.delete(k)
                        purged += 1
            except Exception as e:
                logger.error("Failed invalidating semantic entries for doc %s: %s", doc_id, e)
        return purged

    def clear(self) -> None:
        self._entries.clear()
        if self.enabled and self.client:
            for k in self.client.scan_iter("sem:*"):
                self.client.delete(k)
        self._hits = 0
        self._misses = 0
        self._guard_rejections = 0

    @property
    def stats(self) -> dict[str, int]:
        return {
            "entries": len(self._entries),
            "hits": self._hits,
            "misses": self._misses,
            "guard_rejections": self._guard_rejections,
        }
