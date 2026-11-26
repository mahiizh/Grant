import os
import subprocess
import sys
from pathlib import Path


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
