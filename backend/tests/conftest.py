import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Keep test runs hermetic: no live model calls, no external stores, and all
# evaluation data is written to temp directories, never to tracked files under
# evals/. Set this before importing app.main so the cached Settings pick the
# overrides up.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_DIR = Path(tempfile.mkdtemp(prefix="graphrag-golden-"))
for _name in ("questions.jsonl", "multi_turn.jsonl", "README.md"):
    _source = _REPO_ROOT / "evals" / "golden" / _name
    if _source.exists():
        shutil.copy2(_source, _GOLDEN_DIR / _name)

os.environ["APP_ENV"] = "test"
# An empty value overrides any key loaded from .env, so the mock path is used.
os.environ["GEMINI_API_KEY"] = ""
os.environ["EVAL_GOLDEN_DIR"] = str(_GOLDEN_DIR)
os.environ["EVAL_CANDIDATES_DIR"] = tempfile.mkdtemp(prefix="graphrag-candidates-")
os.environ["LLM_CACHE_DIR"] = tempfile.mkdtemp(prefix="graphrag-llm-cache-")

from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
