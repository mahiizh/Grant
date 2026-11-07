from typing import Any

from app.cache.exact import ExactCache
from app.cache.semantic import SemanticCache


class CacheInvalidator:
    """Coordinates outbox-driven cache invalidation across exact and semantic tiers."""

    def __init__(
        self,
        exact_cache: ExactCache | None = None,
        semantic_cache: SemanticCache | None = None,
        initial_index_version: int = 1,
    ) -> None:
        self.exact_cache = exact_cache or ExactCache()
        self.semantic_cache = semantic_cache or SemanticCache()
        self._current_index_version = initial_index_version

    @property
    def current_index_version(self) -> int:
        return self._current_index_version

    def increment_index_version(self) -> int:
        """Bump the global index version, instantly invalidating all version-keyed cache entries."""
        self._current_index_version += 1
        self.semantic_cache.invalidate_by_version(min_version=self._current_index_version)
        return self._current_index_version

    def handle_outbox_event(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Handle a CACHE_INVALIDATED or DOCUMENT_DELETED event from the outbox."""
        summary: dict[str, Any] = {"event_type": event_type, "invalidated": True}

        if event_type in ("CACHE_INVALIDATED", "DOCUMENT_DELETED"):
            # Bumping index version makes all old exact & semantic keys obsolete
            new_v = self.increment_index_version()
            summary["new_index_version"] = new_v

            tenant_id = payload.get("tenant_id")
            if tenant_id:
                purged = self.exact_cache.invalidate_tenant(tenant_id)
                summary["exact_keys_purged"] = purged

        return summary
