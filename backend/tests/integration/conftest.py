import os

import pytest

# Safety guard: tests must never point at dev stores.
_DEV_DB = "graphrag_lab"
_DEV_QDRANT = "grant_chunks"
_DEV_ENTITY = "grant_entities"


def _assert_test_isolation() -> None:
    db = os.environ.get("POSTGRES_DB", "")
    qc = os.environ.get("QDRANT_COLLECTION", "")
    qe = os.environ.get("QDRANT_ENTITY_COLLECTION", "")
    if db == _DEV_DB or qc == _DEV_QDRANT or qe == _DEV_ENTITY:
        raise RuntimeError(
            "Refusing to run integration tests against dev stores: "
            f"POSTGRES_DB={db} QDRANT_COLLECTION={qc} QDRANT_ENTITY_COLLECTION={qe}"
        )


@pytest.fixture(scope="session", autouse=True)
def _guard_test_isolation() -> None:
    _assert_test_isolation()
