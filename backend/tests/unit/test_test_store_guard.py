import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from app.core.store_guard import (
    ALLOW_DEV_WRITES_ENV,
    DEV_WRITE_TOKEN_ENV,
    DEV_WRITE_TOKEN_HEADER,
    dev_writes_allowed,
    http_write_violations,
)


def test_running_against_dev_db_aborts_before_fixtures_connect() -> None:
    """The session must refuse dev stores before any fixture can connect."""
    backend_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.update(
        {
            "POSTGRES_DB": "graphrag_lab",
            "NEO4J_URI": "bolt://localhost:7687",
            "QDRANT_COLLECTION": "grant_chunks",
            "QDRANT_ENTITY_COLLECTION": "grant_entities",
        }
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "tests/unit/test_test_store_guard.py",
        ],
        cwd=backend_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert "Refusing to run tests against non-test stores" in output
    assert "POSTGRES_DB='graphrag_lab'" in output


def test_helper_script_cannot_construct_a_dev_store_client() -> None:
    """A helper script using app clients must abort before it connects."""
    backend_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "development",
            "POSTGRES_DB": "graphrag_lab",
            "NEO4J_URI": "bolt://localhost:7687",
            "QDRANT_COLLECTION": "grant_chunks",
            "QDRANT_ENTITY_COLLECTION": "grant_entities",
            "REDIS_DB": "0",
        }
    )
    env.pop(ALLOW_DEV_WRITES_ENV, None)

    script = (
        "from app.indexing.qdrant_indexer import QdrantIndexer; "
        "print('CONSTRUCTED', QdrantIndexer())"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert "CONSTRUCTED" not in output
    assert "Refusing to write to non-test stores" in output
    assert "QDRANT_COLLECTION='grant_chunks'" in output


def test_dev_write_token_is_required_for_dev_http_writes(
    monkeypatch: Any,
) -> None:
    dev_settings = SimpleNamespace(
        APP_ENV="development",
        POSTGRES_DB="graphrag_lab",
        QDRANT_COLLECTION="grant_chunks",
        QDRANT_ENTITY_COLLECTION="grant_entities",
        NEO4J_URI="bolt://localhost:7687",
        REDIS_DB=0,
    )
    monkeypatch.delenv(ALLOW_DEV_WRITES_ENV, raising=False)
    monkeypatch.setenv(DEV_WRITE_TOKEN_ENV, "dev-write-secret")

    assert dev_writes_allowed(None) is False
    assert dev_writes_allowed("wrong") is False
    assert dev_writes_allowed("dev-write-secret") is True
    assert http_write_violations(dev_settings)
    assert http_write_violations(dev_settings, "dev-write-secret") == []

    monkeypatch.setenv(ALLOW_DEV_WRITES_ENV, "1")
    assert dev_writes_allowed(None) is True
    assert http_write_violations(dev_settings) == []


def test_http_middleware_blocks_dev_store_writes_without_token(monkeypatch: Any) -> None:
    from app.main import create_app

    dev_settings = SimpleNamespace(
        PROJECT_NAME="guard-test",
        VERSION="0",
        API_V1_PREFIX="/api/v1",
        DEBUG=True,
        APP_ENV="development",
        POSTGRES_DB="graphrag_lab",
        QDRANT_COLLECTION="grant_chunks",
        QDRANT_ENTITY_COLLECTION="grant_entities",
        NEO4J_URI="bolt://localhost:7687",
        REDIS_DB=0,
    )
    monkeypatch.delenv(ALLOW_DEV_WRITES_ENV, raising=False)
    monkeypatch.delenv(DEV_WRITE_TOKEN_ENV, raising=False)
    monkeypatch.setattr("app.main.get_settings", lambda: dev_settings)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/query",
        json={"query": "write something"},
        headers={DEV_WRITE_TOKEN_HEADER: "not-configured"},
    )

    assert response.status_code == 423
    assert "Refusing to write to non-test stores" in response.json()["detail"]
