from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.cache.guards import validate_cache_hit
from app.cache.keys import generate_exact_cache_key
from app.core.acl import ACLScope
from app.domain import Answer
from tests.fakes.in_memory_retrievers import cosine_similarity, text_to_embedding


class FakeExactCache:
    """In-memory exact-match cache fake."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._hits = 0
        self._misses = 0

    def get(
        self,
        query: str,
        acl_scope: ACLScope,
        index_version: int = 1,
        prompt_version: str = "v1",
        owner_user_id: str | None = None,
    ) -> Answer | None:
        key = generate_exact_cache_key(
            query=query,
            acl_scope=acl_scope,
            index_version=index_version,
            prompt_version=prompt_version,
            owner_user_id=owner_user_id,
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
        )

    def set(
        self,
        query: str,
        answer: Answer,
        acl_scope: ACLScope,
        index_version: int = 1,
        prompt_version: str = "v1",
        owner_user_id: str | None = None,
    ) -> str:
        key = generate_exact_cache_key(
            query=query,
            acl_scope=acl_scope,
            index_version=index_version,
            prompt_version=prompt_version,
            owner_user_id=owner_user_id,
        )
        self._store[key] = {
            "answer": answer,
            "cached_at": datetime.now(UTC),
            "hit_count": 0,
            "tenant_id": acl_scope.tenant_id,
        }
        return key

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


@dataclass
class FakeSemanticCacheEntry:
    query: str
    embedding: list[float]
    answer: Answer
    acl_scope: ACLScope
    index_version: int
    tenant_id: str
    prompt_version: str = "v1"
    as_of: str | None = None
    owner_user_id: str | None = None


class FakeSemanticCache:
    """In-memory semantic cache fake."""

    def __init__(self, similarity_threshold: float = 0.45) -> None:
        self.threshold = similarity_threshold
        self._entries: list[FakeSemanticCacheEntry] = []
        self._hits = 0
        self._misses = 0
        self._guard_rejections = 0

    def get(
        self,
        query: str,
        acl_scope: ACLScope,
        index_version: int = 1,
        prompt_version: str = "v1",
        as_of: str | None = None,
        owner_user_id: str | None = None,
    ) -> Answer | None:
        if not self._entries:
            self._misses += 1
            return None

        query_embedding = text_to_embedding(query, dim=384)
        best_entry: FakeSemanticCacheEntry | None = None
        best_similarity = 0.0

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

            similarity = cosine_similarity(query_embedding, entry.embedding)
            if similarity < self.threshold or similarity <= best_similarity:
                continue

            guard_result = validate_cache_hit(
                new_query=query,
                cached_query=entry.query,
            )
            if not guard_result.passed:
                self._guard_rejections += 1
                continue

            best_entry = entry
            best_similarity = similarity

        if best_entry is None:
            self._misses += 1
            return None

        self._hits += 1
        return Answer(
            query=query,
            answer=best_entry.answer.answer,
            evidence=best_entry.answer.evidence,
            is_abstention=best_entry.answer.is_abstention,
            router_strategy="semantic_cache",
            cost_usd=0.0,
            latency_ms=4.5,
        )

    def set(
        self,
        query: str,
        answer: Answer,
        acl_scope: ACLScope,
        index_version: int = 1,
        prompt_version: str = "v1",
        as_of: str | None = None,
        owner_user_id: str | None = None,
    ) -> None:
        entry = FakeSemanticCacheEntry(
            query=query,
            embedding=text_to_embedding(query, dim=384),
            answer=answer,
            acl_scope=acl_scope,
            index_version=index_version,
            tenant_id=acl_scope.tenant_id,
            prompt_version=prompt_version,
            as_of=as_of,
            owner_user_id=owner_user_id,
        )
        self._entries.append(entry)

    def clear(self) -> None:
        self._entries.clear()
        self._hits = 0
        self._misses = 0
        self._guard_rejections = 0

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "entries": len(self._entries),
            "hits": self._hits,
            "misses": self._misses,
            "guard_rejections": self._guard_rejections,
        }
