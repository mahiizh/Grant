import json
import logging
from typing import Any

import redis

from app.cache.exact import ExactCache, _owner_version_key
from app.cache.keys import DEFAULT_INDEX_VERSION
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CacheInvalidator:
    """Coordinates outbox-driven invalidation of the exact cache tier.

    Index versions live in Redis, one counter per owner, so the API process can
    see bumps made by the ingestion worker. A supplied exact cache shares its
    Redis client; otherwise the invalidator connects directly.
    """

    def __init__(
        self,
        exact_cache: ExactCache | None = None,
        initial_index_version: int = DEFAULT_INDEX_VERSION,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self.exact_cache = exact_cache
        self._current_index_version = initial_index_version
        self._redis: redis.Redis | None = redis_client
        if self._redis is None and exact_cache is not None:
            self._redis = exact_cache.client
        if self._redis is None:
            try:
                self._redis = redis.Redis.from_url(get_settings().redis_url)
            except Exception as e:  # pragma: no cover - defensive connection guard
                logger.warning("Failed connecting to Redis for CacheInvalidator: %s", e)
                self._redis = None

    @property
    def current_index_version(self) -> int:
        """Legacy in-process counter, retained for diagnostics."""
        return self._current_index_version

    def increment_index_version(self) -> int:
        """Bump the legacy in-process counter."""
        self._current_index_version += 1
        return self._current_index_version

    def current_owner_index_version(self, owner_user_id: str | None) -> int:
        """Read the per-owner version used by exact cache keys."""
        if self._redis is None:
            return DEFAULT_INDEX_VERSION
        try:
            raw = self._redis.get(_owner_version_key(owner_user_id))
            return int(raw) if raw is not None else DEFAULT_INDEX_VERSION
        except Exception as e:
            logger.warning("Failed reading index version for %s: %s", owner_user_id, e)
            return DEFAULT_INDEX_VERSION

    def increment_owner_index_version(self, owner_user_id: str | None) -> int:
        """Atomically bump the per-owner version after an index mutation."""
        legacy_version = self.increment_index_version()
        if self._redis is None:
            return legacy_version
        try:
            return int(self._redis.incr(_owner_version_key(owner_user_id)))
        except Exception as e:
            logger.error("Failed incrementing index version for %s: %s", owner_user_id, e)
            return legacy_version

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
        """Handle a cache invalidation event from the outbox."""
        summary: dict[str, Any] = {"event_type": event_type, "invalidated": False}

        if event_type in ("CACHE_INVALIDATED", "DOCUMENT_DELETED"):
            summary["invalidated"] = True
            summary["new_index_version"] = self.increment_owner_index_version(
                payload.get("owner_user_id")
            )
            summary["owner_user_id"] = payload.get("owner_user_id") or "anon"

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

        return summary
