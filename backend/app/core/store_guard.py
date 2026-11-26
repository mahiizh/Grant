"""Shared guard for test and helper processes that can write backing stores.

The pytest guard used to live only in ``backend/tests/conftest.py``. A helper
script could still import an application client (or call the API) while the
settings pointed at the developer stores. This module is the single source of
truth for that decision and is used by:

* pytest, before fixtures import ``app.main``;
* application store clients, before they construct real Qdrant/Neo4j/Postgres
  clients;
* the API write middleware, before an HTTP write reaches a route.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

DEV_POSTGRES_DB = "graphrag_lab"
DEV_QDRANT_COLLECTIONS = frozenset({"grant_chunks", "grant_entities"})
DEV_NEO4J_PORT = 7687
DEV_REDIS_DB = 0
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

ALLOW_DEV_WRITES_ENV = "GRAPHRAG_ALLOW_DEV_WRITES"
DEV_WRITE_TOKEN_ENV = "GRAPHRAG_DEV_WRITE_TOKEN"
DEV_WRITE_TOKEN_HEADER = "X-Dev-Write-Token"

PYTEST_REFUSAL = "Refusing to run tests against non-test stores"
WRITE_REFUSAL = "Refusing to write to non-test stores"


class StoreGuardError(RuntimeError):
    """Raised before a non-test store client can be created."""


def _is_test_mode(settings: Any) -> bool:
    return str(getattr(settings, "APP_ENV", "")).lower() == "test"


def _neo4j_port(uri: str) -> int | None:
    try:
        return urlparse(uri).port
    except ValueError:
        return None


def store_violations(settings: Any) -> list[str]:
    """Return human-readable reasons why ``settings`` targets a non-test store.

    Test mode is strict: every store must be the dedicated test target. Live
    mode only flags the known developer targets, so staging/production configs
    are not silently treated as unsafe test writes.
    """
    violations: list[str] = []
    test_mode = _is_test_mode(settings)

    postgres_db = str(getattr(settings, "POSTGRES_DB", ""))
    if test_mode:
        if not postgres_db.endswith("_test"):
            violations.append(f"POSTGRES_DB={postgres_db!r} must end with '_test'")
    elif postgres_db == DEV_POSTGRES_DB:
        violations.append(f"POSTGRES_DB={postgres_db!r} is the developer database")

    for name in ("QDRANT_COLLECTION", "QDRANT_ENTITY_COLLECTION"):
        collection = str(getattr(settings, name, ""))
        if test_mode:
            if not collection.endswith("_test"):
                violations.append(f"{name}={collection!r} must end with '_test'")
        elif collection in DEV_QDRANT_COLLECTIONS:
            violations.append(f"{name}={collection!r} is a developer collection")

    neo4j_uri = str(getattr(settings, "NEO4J_URI", ""))
    port = _neo4j_port(neo4j_uri)
    if test_mode:
        if port != 7688:
            violations.append(f"NEO4J_URI={neo4j_uri!r} must use port 7688")
    elif port == DEV_NEO4J_PORT:
        violations.append(f"NEO4J_URI={neo4j_uri!r} is the developer Neo4j instance")

    redis_db = int(getattr(settings, "REDIS_DB", 0) or 0)
    if test_mode:
        if redis_db == DEV_REDIS_DB:
            violations.append(f"REDIS_DB={redis_db!r} must not be the developer Redis database")
    elif redis_db == DEV_REDIS_DB:
        violations.append(f"REDIS_DB={redis_db!r} is the developer Redis database")

    return violations


def dev_writes_allowed(header_token: str | None = None) -> bool:
    """A developer-store write needs an explicit process or request opt-in."""
    if os.getenv(ALLOW_DEV_WRITES_ENV, "").lower() in {"1", "true", "yes"}:
        return True
    expected = os.getenv(DEV_WRITE_TOKEN_ENV, "")
    return bool(expected) and bool(header_token) and header_token == expected


def assert_writable_stores(settings: Any) -> None:
    """Block before any client connects if the resolved stores are unsafe."""
    violations = store_violations(settings)
    if violations and not dev_writes_allowed():
        raise StoreGuardError(f"{WRITE_REFUSAL}: " + "; ".join(violations))


def assert_test_stores(settings: Any) -> None:
    """Strict pytest guard; returns the same violations with a test-specific prefix."""
    violations = store_violations(settings)
    if violations:
        raise StoreGuardError(f"{PYTEST_REFUSAL}: " + "; ".join(violations))


def http_write_violations(settings: Any, header_token: str | None = None) -> list[str]:
    """Return violations for an HTTP write, honouring the explicit token header."""
    if dev_writes_allowed(header_token):
        return []
    return store_violations(settings)
