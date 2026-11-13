from collections.abc import Iterator
from typing import Any


class FakeRedis:
    """Minimal in-memory stand-in for the Redis client methods the caches use.

    Supports the subset used by ``ExactCache``, ``SemanticCache`` and
    ``CacheInvalidator``: ``get``, ``set``, ``delete``, ``scan_iter`` and
    ``keys``. Values are stored as UTF-8 bytes so callers exercise the same
    decode path they would with a real Redis server.
    """

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def get(self, key: str) -> bytes | None:
        return self.store.get(key)

    def set(self, key: str, value: str | bytes, ex: int | None = None) -> bool:
        self.store[key] = value.encode("utf-8") if isinstance(value, str) else value
        return True

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                deleted += 1
        return deleted

    def keys(self, pattern: str = "*") -> list[str]:
        return list(self.scan_iter(pattern))

    def scan_iter(self, pattern: str = "*") -> Iterator[str]:
        prefix = pattern.rstrip("*")
        for key in list(self.store):
            if pattern == "*" or key.startswith(prefix):
                yield key

    def seed(self, key: str, value: Any) -> None:
        self.set(key, value)
