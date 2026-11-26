import asyncio
from collections.abc import Generator

import pytest
from neo4j import AsyncGraphDatabase
from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings
from app.db.models import Base
from app.db.postgres import get_engine, init_db


async def _prepare_integration_stores() -> None:
    """Reset only the isolated test stores before live integration tests."""
    settings = get_settings()

    qdrant = AsyncQdrantClient(
        url=f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}",
        check_compatibility=False,
    )
    try:
        for name in (settings.QDRANT_COLLECTION, settings.QDRANT_ENTITY_COLLECTION):
            if await qdrant.collection_exists(name):
                await qdrant.delete_collection(name)

        await qdrant.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config={
                "dense": models.VectorParams(
                    size=settings.EMBEDDING_DIM,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={"sparse": models.SparseVectorParams()},
        )
        await qdrant.create_collection(
            collection_name=settings.QDRANT_ENTITY_COLLECTION,
            vectors_config=models.VectorParams(
                size=settings.EMBEDDING_DIM,
                distance=models.Distance.COSINE,
            ),
        )
    finally:
        await qdrant.close()

    neo4j = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )
    try:
        async with neo4j.session(database=settings.NEO4J_DATABASE) as session:
            await session.run("MATCH (n) DETACH DELETE n")
    finally:
        await neo4j.close()

    await init_db()
    engine = get_engine()
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest.fixture(scope="session", autouse=True)
def integration_stores() -> Generator[None, None, None]:
    """Guarantee integration tests never observe leftovers from another run."""
    asyncio.run(_prepare_integration_stores())
    yield
