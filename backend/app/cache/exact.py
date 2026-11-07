import contextlib
import json
import logging

import redis

from app.cache.keys import generate_exact_cache_key
from app.core.acl import ACLScope
from app.core.config import get_settings
from app.domain import Answer, Evidence, Provenance, SourceTier

logger = logging.getLogger(__name__)


class ExactCache:
    """Production Redis-backed exact-match response cache."""

    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        settings = get_settings()
        self._hits = 0
        self._misses = 0
        self.client: redis.Redis | None = None
        try:
            self.client = redis_client or redis.Redis.from_url(settings.redis_url)
        except Exception as e:
            logger.warning("Failed connecting to Redis for ExactCache: %s", e)
            self.client = None

    def get(
        self,
        query: str,
        acl_scope: ACLScope,
        index_version: int = 1,
        prompt_version: str = "v1",
    ) -> Answer | None:
        """Retrieve cached Answer if exact key matches in Redis."""
        key = generate_exact_cache_key(
            query=query,
            acl_scope=acl_scope,
            index_version=index_version,
            prompt_version=prompt_version,
        )
        if not self.client:
            self._misses += 1
            return None

        try:
            raw = self.client.get(f"exact:{key}")
            if not raw:
                self._misses += 1
                return None

            raw_str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            data = json.loads(raw_str)
            self._hits += 1

            evidence_items = []
            for ev_data in data.get("evidence", []):
                prov_data = ev_data.get("provenance", {})
                prov = Provenance(
                    tier=SourceTier(prov_data.get("tier", 1)),
                    source_uri=prov_data.get("source_uri", ""),
                    confidence=prov_data.get("confidence", 1.0),
                    verified=prov_data.get("verified", True),
                )
                method = ev_data.get("retrieval_method", "hybrid")
                if method not in ("dense", "sparse", "graph", "hybrid", "rerank"):
                    method = "hybrid"
                evidence_items.append(
                    Evidence(
                        chunk_id=ev_data["chunk_id"],
                        doc_id=ev_data["doc_id"],
                        text=ev_data["text"],
                        score=ev_data.get("score", 1.0),
                        retrieval_method=method,
                        provenance=prov,
                    )
                )

            return Answer(
                query=query,
                answer=data["answer"],
                evidence=evidence_items,
                is_abstention=data.get("is_abstention", False),
                router_strategy="cache",
                cost_usd=0.0,
                latency_ms=1.2,
            )
        except Exception as e:
            logger.error("Error reading from Redis exact cache: %s", e)
            self._misses += 1
            return None

    def set(
        self,
        query: str,
        answer: Answer,
        acl_scope: ACLScope,
        index_version: int = 1,
        prompt_version: str = "v1",
        ttl_seconds: int = 3600,
    ) -> str:
        """Store synthesized answer under isolated permission and index-version key in Redis."""
        key = generate_exact_cache_key(
            query=query,
            acl_scope=acl_scope,
            index_version=index_version,
            prompt_version=prompt_version,
        )
        if not self.client:
            return key

        try:
            evidence_dicts = [
                {
                    "chunk_id": ev.chunk_id,
                    "doc_id": ev.doc_id,
                    "text": ev.text,
                    "score": ev.score,
                    "retrieval_method": ev.retrieval_method,
                    "provenance": {
                        "tier": int(ev.provenance.tier),
                        "source_uri": ev.provenance.source_uri,
                        "confidence": ev.provenance.confidence,
                        "verified": ev.provenance.verified,
                    },
                }
                for ev in answer.evidence
            ]

            payload = {
                "query": query,
                "answer": answer.answer,
                "evidence": evidence_dicts,
                "is_abstention": answer.is_abstention,
                "tenant_id": acl_scope.tenant_id,
            }

            self.client.set(f"exact:{key}", json.dumps(payload), ex=ttl_seconds)
        except Exception as e:
            logger.error("Error writing to Redis exact cache: %s", e)

        return key

    def invalidate_tenant(self, tenant_id: str) -> int:
        """Purge cached responses for a tenant."""
        if not self.client:
            return 0
        count = 0
        for k in self.client.scan_iter("exact:*"):
            raw = self.client.get(k)
            if raw:
                raw_str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                if f'"tenant_id": "{tenant_id}"' in raw_str:
                    self.client.delete(k)
                    count += 1
        return count

    def clear(self) -> None:
        if self.client:
            for k in self.client.scan_iter("exact:*"):
                self.client.delete(k)
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> dict[str, int]:
        count = 0
        if self.client:
            with contextlib.suppress(Exception):
                count = sum(1 for _ in self.client.scan_iter("exact:*"))
        return {
            "entries": count,
            "hits": self._hits,
            "misses": self._misses,
        }
