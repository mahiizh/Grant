import json
import logging
from typing import Any

import redis

from app.cache.exact import ExactCache
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CacheInvalidator:
    """Coordinates outbox-driven invalidation of the exact cache tier.

    When an exact cache instance is supplied it is purged in-process. Otherwise
    the invalidator talks to Redis directly so a worker process can delete keys
    written by another process.
    """

    def __init__(
        self,
        exact_cache: ExactCache | None = None,
        initial_index_version: int = 1,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self.exact_cache = exact_cache
        self._current_index_version = initial_index_version
        self._redis: redis.Redis | None = redis_client
        if exact_cache is None:
            try:
                self._redis = redis_client or redis.Redis.from_url(get_settings().redis_url)
            except Exception as e:  # pragma: no cover - defensive connection guard
                logger.warning("Failed connecting to Redis for CacheInvalidator: %s", e)
                self._redis = None

    @property
    def current_index_version(self) -> int:
        return self._current_index_version

    def increment_index_version(self) -> int:
        """Bump the global index version, instantly invalidating version-keyed entries."""
        self._current_index_version += 1
        return self._current_index_version

    def _document_keys(self, doc_id: str) -> list[str]:
        """Return exact Redis keys whose evidence cites ``doc_id``."""
        if self._redis is None:
            return []
        keys: list[str] = []
        try:
            for k in self._redis.scan_iter("exact:*"):
                raw = self._redis.get(k)
                if not raw:
                    continue
                raw_str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                data = json.loads(raw_str)
                if any(ev.get("doc_id") == doc_id for ev in data.get("evidence", [])):
                    keys.append(k)
        except Exception as e:
            logger.error("Failed scanning Redis cache for doc %s: %s", doc_id, e)
        return keys

    def _purge_redis_document(self, doc_id: str) -> int:
        """Delete exact Redis keys whose evidence cites ``doc_id``."""
        keys = self._document_keys(doc_id)
        for key in keys:
            self._redis.delete(key)  # type: ignore[union-attr]
        return len(keys)

    def count_document_keys(self, doc_id: str) -> int:
        """Count cache entries that still cite ``doc_id``."""
        if self._redis is None:
            return 0
        return len(self._document_keys(doc_id))

    def handle_outbox_event(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Handle a CACHE_INVALIDATED or DOCUMENT_DELETED event from the outbox."""
        summary: dict[str, Any] = {"event_type": event_type, "invalidated": True}

        if event_type in ("CACHE_INVALIDATED", "DOCUMENT_DELETED"):
            summary["new_index_version"] = self.increment_index_version()

            doc_id = payload.get("doc_id")
            if doc_id:
                if self.exact_cache is not None:
                    summary["exact_keys_purged"] = self.exact_cache.invalidate_document(doc_id)
                else:
                    summary["redis_keys_purged"] = self._purge_redis_document(doc_id)

            if self.exact_cache is not None:
                shared_scope = payload.get("shared_scope")
                if shared_scope:
                    summary["exact_keys_purged"] = summary.get(
                        "exact_keys_purged", 0
                    ) + self.exact_cache.invalidate_shared_scope(shared_scope)

                owner_user_id = payload.get("owner_user_id")
                if owner_user_id:
                    summary["exact_keys_purged"] = summary.get(
                        "exact_keys_purged", 0
                    ) + self.exact_cache.invalidate_owner(owner_user_id)

        return summary
