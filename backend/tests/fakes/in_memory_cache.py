from datetime import UTC, datetime
from typing import Any

from app.cache.keys import DEFAULT_INDEX_VERSION, generate_exact_cache_key
from app.core.acl import ACLScope
from app.domain import Answer


class FakeExactCache:
    """In-memory exact-match cache fake keyed by owner/shared ACL boundary."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._hits = 0
        self._misses = 0
        self.index_versions: dict[str, int] = {}

    def current_index_version(self, owner_user_id: str | None = None) -> int:
        return self.index_versions.get(owner_user_id or "anon", DEFAULT_INDEX_VERSION)

    def get(
        self,
        query: str,
        acl_scope: ACLScope | None = None,
        index_version: int = DEFAULT_INDEX_VERSION,
        prompt_version: str = "v1",
        owner_user_id: str | None = None,
        answer_policy: str | None = None,
    ) -> Answer | None:
        key = generate_exact_cache_key(
            query=query,
            acl_scope=acl_scope,
            index_version=index_version,
            prompt_version=prompt_version,
            owner_user_id=owner_user_id,
            answer_policy=answer_policy,
        )
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None

        self._hits += 1
        entry["hit_count"] += 1
        original_answer: Answer = entry["answer"]
        return Answer(
            query=query,
            answer=original_answer.answer,
            evidence=original_answer.evidence,
            is_abstention=original_answer.is_abstention,
            router_strategy="cache",
            cost_usd=0.0,
            latency_ms=1.5,
            source_kind=original_answer.source_kind,
            web_sources=list(original_answer.web_sources or []),
        )

    def set(
        self,
        query: str,
        answer: Answer,
        acl_scope: ACLScope | None = None,
        index_version: int = DEFAULT_INDEX_VERSION,
        prompt_version: str = "v1",
        ttl_seconds: int | None = None,
        owner_user_id: str | None = None,
        answer_policy: str | None = None,
    ) -> str:
        key = generate_exact_cache_key(
            query=query,
            acl_scope=acl_scope,
            index_version=index_version,
            prompt_version=prompt_version,
            owner_user_id=owner_user_id,
            answer_policy=answer_policy,
        )
        self._store[key] = {
            "answer": answer,
            "cached_at": datetime.now(UTC),
            "hit_count": 0,
            "owner_user_id": owner_user_id,
            "shared_scope": acl_scope.shared_scope if acl_scope else None,
        }
        return key

    def invalidate_document(self, doc_id: str) -> int:
        return self._invalidate(
            lambda entry: any(ev.doc_id == doc_id for ev in entry["answer"].evidence)
        )

    def invalidate_owner(self, owner_user_id: str) -> int:
        return self._invalidate(lambda entry: entry["owner_user_id"] == owner_user_id)

    def invalidate_shared_scope(self, shared_scope: str) -> int:
        return self._invalidate(lambda entry: entry["shared_scope"] == shared_scope)

    def _invalidate(self, predicate: Any) -> int:
        matches = [key for key, entry in self._store.items() if predicate(entry)]
        for key in matches:
            self._store.pop(key, None)
        return len(matches)

    def clear(self) -> None:
        self._store.clear()
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> dict[str, int]:
        return {
            "entries": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
        }
