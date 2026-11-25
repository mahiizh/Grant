import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Keep test runs hermetic: no live model calls, no external stores, and all
# evaluation data is written to temp directories, never to tracked files under
# evals/. Set this before importing app.main so the cached Settings pick the
# overrides up.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_DIR = Path(tempfile.mkdtemp(prefix="graphrag-golden-"))
for _source in sorted((_REPO_ROOT / "evals" / "golden").glob("*")):
    if _source.is_file():
        shutil.copy2(_source, _GOLDEN_DIR / _source.name)

os.environ["APP_ENV"] = "test"
# An empty value overrides any key loaded from .env, so the mock path is used.
os.environ["GEMINI_API_KEY"] = ""
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
os.environ["EVAL_GOLDEN_DIR"] = str(_GOLDEN_DIR)
os.environ["EVAL_CANDIDATES_DIR"] = tempfile.mkdtemp(prefix="graphrag-candidates-")
os.environ["LLM_CACHE_DIR"] = tempfile.mkdtemp(prefix="graphrag-llm-cache-")

# Test isolation: never touch dev stores. Allow explicit override via env.
os.environ.setdefault("POSTGRES_DB", "graphrag_lab_test")
os.environ.setdefault("QDRANT_COLLECTION", "grant_chunks_test")
os.environ.setdefault("QDRANT_ENTITY_COLLECTION", "grant_entities_test")
os.environ.setdefault("NEO4J_DATABASE", os.environ.get("NEO4J_TEST_DATABASE", "neo4j"))
os.environ.setdefault("NEO4J_URI", os.environ.get("NEO4J_TEST_URI", "bolt://localhost:7688"))

from app.main import create_app  # noqa: E402
from tests.fakes.fake_web import FakeWebClient, FakeWebIngestor  # noqa: E402


@pytest.fixture(autouse=True)
def mock_graspreach(monkeypatch: pytest.MonkeyPatch) -> Generator[Any, None, None]:
    """No test may reach the real web; inject configurable in-memory fakes."""
    from app.acquisition import web as web_module
    from app.acquisition import web_ingest as web_ingest_module
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
