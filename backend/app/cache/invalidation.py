import json
import logging
from typing import Any

import redis

from app.cache.exact import ExactCache
from app.cache.semantic import SemanticCache
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CacheInvalidator:
    """Coordinates outbox-driven cache invalidation across exact and semantic tiers.

    When cache instances are supplied they are purged in-process. Otherwise the
    invalidator talks to Redis directly so a worker process can delete keys
    written by another process without loading the embedding model.
    """

    def __init__(
        self,
        exact_cache: ExactCache | None = None,
        semantic_cache: SemanticCache | None = None,
        initial_index_version: int = 1,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self.exact_cache = exact_cache
        self.semantic_cache = semantic_cache
        self._current_index_version = initial_index_version
        self._redis: redis.Redis | None = redis_client
        if exact_cache is None and semantic_cache is None:
            try:
                self._redis = redis_client or redis.Redis.from_url(get_settings().redis_url)
            except Exception as e:  # pragma: no cover - defensive connection guard
                logger.warning("Failed connecting to Redis for CacheInvalidator: %s", e)
                self._redis = None

    @property
    def current_index_version(self) -> int:
        return self._current_index_version

    def increment_index_version(self) -> int:
        """Bump the global index version, instantly invalidating all version-keyed cache entries."""
        self._current_index_version += 1
        if self.semantic_cache is not None:
            self.semantic_cache.invalidate_by_version(min_version=self._current_index_version)
        return self._current_index_version

    def _purge_redis_document(self, doc_id: str) -> int:
        """Delete exact and semantic Redis keys whose evidence cites ``doc_id``."""
        if self._redis is None:
            return 0
        count = 0
        try:
            for prefix in ("exact:*", "sem:*"):
                for k in self._redis.scan_iter(prefix):
                    raw = self._redis.get(k)
                    if not raw:
                        continue
                    raw_str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                    data = json.loads(raw_str)
                    if any(ev.get("doc_id") == doc_id for ev in data.get("evidence", [])):
                        self._redis.delete(k)
                        count += 1
        except Exception as e:
            logger.error("Failed purging Redis cache for doc %s: %s", doc_id, e)
        return count

    def handle_outbox_event(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Handle a CACHE_INVALIDATED or DOCUMENT_DELETED event from the outbox."""
        summary: dict[str, Any] = {"event_type": event_type, "invalidated": True}

        if event_type in ("CACHE_INVALIDATED", "DOCUMENT_DELETED"):
            # Bumping the index version makes old version-keyed entries obsolete.
            summary["new_index_version"] = self.increment_index_version()

            doc_id = payload.get("doc_id")
            if doc_id:
                if self.exact_cache is not None:
                    summary["exact_keys_purged"] = self.exact_cache.invalidate_document(doc_id)
                if self.semantic_cache is not None:
                    summary["semantic_keys_purged"] = self.semantic_cache.invalidate_document(
                        doc_id
                    )
                if self.exact_cache is None and self.semantic_cache is None:
                    summary["redis_keys_purged"] = self._purge_redis_document(doc_id)

            tenant_id = payload.get("tenant_id")
            if tenant_id and self.exact_cache is not None:
                summary["exact_keys_purged"] = summary.get(
                    "exact_keys_purged", 0
                ) + self.exact_cache.invalidate_tenant(tenant_id)

        return summary
