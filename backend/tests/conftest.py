import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Keep test runs hermetic: no live model calls, no external stores, and all
# evaluation data is written to temp directories, never to tracked files.
# Set this before importing app.main so the cached Settings pick the overrides up.
os.environ["APP_ENV"] = "test"
# An empty value overrides any key loaded from .env, so the mock path is used.
os.environ["GEMINI_API_KEY"] = ""
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
os.environ["EVAL_GOLDEN_DIR"] = tempfile.mkdtemp(prefix="graphrag-golden-")
os.environ["EVAL_CANDIDATES_DIR"] = tempfile.mkdtemp(prefix="graphrag-candidates-")
os.environ["LLM_CACHE_DIR"] = tempfile.mkdtemp(prefix="graphrag-llm-cache-")

# Test isolation: never touch dev stores. Allow explicit override via env.
os.environ.setdefault("POSTGRES_DB", "graphrag_lab_test")
os.environ.setdefault("QDRANT_COLLECTION", "grant_chunks_test")
os.environ.setdefault("QDRANT_ENTITY_COLLECTION", "grant_entities_test")
os.environ.setdefault("NEO4J_DATABASE", os.environ.get("NEO4J_TEST_DATABASE", "neo4j"))
os.environ.setdefault("NEO4J_URI", os.environ.get("NEO4J_TEST_URI", "bolt://localhost:7688"))
os.environ.setdefault("REDIS_DB", "1")

from app.core.config import get_settings  # noqa: E402
from app.core.store_guard import StoreGuardError, assert_test_stores  # noqa: E402

try:
    assert_test_stores(get_settings())
except StoreGuardError as exc:
    pytest.exit(str(exc), returncode=3)

from app.main import create_app  # noqa: E402
from tests.fakes.fake_web import FakeWebClient, FakeWebIngestor  # noqa: E402


@pytest.fixture(autouse=True)
def mock_graspreach(monkeypatch: pytest.MonkeyPatch) -> Generator[Any, None, None]:
    """No test may reach the real web; inject configurable in-memory fakes."""
    from app.web_grounding import web as web_module
    from app.web_grounding import web_ingest as web_ingest_module
    from app.orchestration import workflow as workflow_module

    client = FakeWebClient()
    ingestor = FakeWebIngestor()
    harness = SimpleNamespace(client=client, ingestor=ingestor)

    monkeypatch.setattr(web_module, "get_web_client", lambda: client)
    monkeypatch.setattr(web_module, "set_web_client", lambda _client: None)
    monkeypatch.setattr(web_ingest_module, "get_web_ingestor", lambda: ingestor)
    monkeypatch.setattr(web_ingest_module, "set_web_ingestor", lambda _ingestor: None)
    monkeypatch.setattr(workflow_module, "get_web_client", lambda: client)
    monkeypatch.setattr(workflow_module, "get_web_ingestor", lambda: ingestor)
    yield harness


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def tmp_corpus_dir(tmp_path: Path) -> Path:
    """Create a small caller-owned corpus so tests never depend on demo assets."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    documents = {
        "rfc_001_storage_architecture.md": """# RFC 001: Storage Architecture
**Document ID**: `doc_rfc_storage_001`

## Overview
PostgreSQL 16 is the single source of truth. OutboxWorker stages events in the PostgreSQL outbox.
Alice Chen leads the Data Platform Team. Redis caches exact answers.
""",
        "postmortem_inc_2026_04.md": """# Postmortem INC-2026-04
**Document ID**: `doc_postmortem_inc_04`

## Impact
INC-2026-04 degraded PaymentGateway with a 24% failure rate. Bob Kumar coordinated the response.
Qdrant and Neo4j were synchronized after the fix.
""",
        "team_directory_2026.md": """# Team Directory
**Document ID**: `doc_team_directory_2026`

## Teams
The Data Platform Team owns PostgreSQL. The Payments Team owns PaymentGateway.
Elena Rostova coordinates with Bob Kumar during incidents.
""",
    }
    for filename, content in documents.items():
        (corpus / filename).write_text(content, encoding="utf-8")
    return corpus
