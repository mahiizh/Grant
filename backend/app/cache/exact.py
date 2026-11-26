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

    def __init__(self, redis_client: redis.Redis | None = None, enabled: bool = True) -> None:
        settings = get_settings()
        self.enabled = enabled
        self._hits = 0
        self._misses = 0
        self.client: redis.Redis | None = None
        if not self.enabled:
            return
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
        owner_user_id: str | None = None,
    ) -> Answer | None:
        """Retrieve cached Answer if exact key matches in Redis."""
        if not self.enabled:
            self._misses += 1
            return None
        key = generate_exact_cache_key(
            query=query,
            acl_scope=acl_scope,
            index_version=index_version,
            prompt_version=prompt_version,
            owner_user_id=owner_user_id,
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
                if method not in ("dense", "sparse", "graph", "hybrid", "rerank", "web"):
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
                source_kind=data.get("source_kind", "docs"),
                web_sources=list(data.get("web_sources", []) or []),
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
        owner_user_id: str | None = None,
    ) -> str:
        """Store synthesized answer under isolated permission and index-version key in Redis."""
        key = generate_exact_cache_key(
            query=query,
            acl_scope=acl_scope,
            index_version=index_version,
            prompt_version=prompt_version,
            owner_user_id=owner_user_id,
        )
        if not self.enabled or not self.client:
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
                "source_kind": answer.source_kind,
                "web_sources": list(answer.web_sources or []),
                "acl_scope": acl_scope.model_dump(mode="json"),
                "shared_scope": acl_scope.shared_scope,
                "owner_user_id": owner_user_id,
            }

            self.client.set(f"exact:{key}", json.dumps(payload), ex=ttl_seconds)
        except Exception as e:
            logger.error("Error writing to Redis exact cache: %s", e)

        return key

    def invalidate_document(self, doc_id: str) -> int:
        """Purge cached answers whose evidence cites ``doc_id``."""
        if not self.enabled or not self.client:
            return 0
        count = 0
        try:
            for k in self.client.scan_iter("exact:*"):
                raw = self.client.get(k)
                if not raw:
                    continue
                raw_str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                data = json.loads(raw_str)
                if any(ev.get("doc_id") == doc_id for ev in data.get("evidence", [])):
                    self.client.delete(k)
                    count += 1
        except Exception as e:
            logger.error("Error invalidating exact cache for doc %s: %s", doc_id, e)
        return count

    def invalidate_shared_scope(self, shared_scope: str) -> int:
        """Purge cached responses written under a named shared scope."""
        return self._invalidate_field("shared_scope", shared_scope)

    def invalidate_owner(self, owner_user_id: str) -> int:
        """Purge cached responses written for one owner."""
        return self._invalidate_field("owner_user_id", owner_user_id)

    def _invalidate_field(self, field: str, value: str) -> int:
        if not self.enabled or not self.client:
            return 0
        count = 0
        for k in self.client.scan_iter("exact:*"):
            raw = self.client.get(k)
            if not raw:
                continue
            raw_str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            try:
                data = json.loads(raw_str)
            except json.JSONDecodeError:
                continue
            if data.get(field) == value:
                self.client.delete(k)
                count += 1
        return count

    def clear(self) -> None:
        if self.enabled and self.client:
            for k in self.client.scan_iter("exact:*"):
                self.client.delete(k)
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> dict[str, int]:
        count = 0
        if self.enabled and self.client:
            with contextlib.suppress(Exception):
                count = sum(1 for _ in self.client.scan_iter("exact:*"))
        return {
            "entries": count,
            "hits": self._hits,
            "misses": self._misses,
        }
