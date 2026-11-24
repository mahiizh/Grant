import logging
from typing import Any

import redis.asyncio as aioredis
from neo4j import AsyncGraphDatabase
from qdrant_client import AsyncQdrantClient, models
from sqlalchemy import text

from app.core.config import get_settings
from app.db.postgres import announce_database_identity, get_engine, verify_schema

logger = logging.getLogger(__name__)


async def verify_infrastructure_live() -> None:
    """Validate all real stores and keys at startup in live mode (APP_ENV != 'test').

    Refuses to start if GEMINI_API_KEY is missing, or if Postgres, Qdrant, Neo4j,
    or Redis are unreachable, or if the Qdrant vector size doesn't match EMBEDDING_DIM.
    """
    settings = get_settings()
    if settings.APP_ENV == "test":
        logger.info("Test environment detected; skipping live infrastructure verification.")
        return

    logger.info("Validating live infrastructure and API keys...")

    # 1. Gemini API Key
    if not settings.GEMINI_API_KEY or not settings.GEMINI_API_KEY.strip():
        raise RuntimeError(
            "Startup failed: GEMINI_API_KEY is required in live mode (APP_ENV != 'test')."
        )

    # 2. PostgreSQL
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        raise RuntimeError(
            f"Startup failed: PostgreSQL is unreachable at "
            f"{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}: {e}"
        ) from e

    await announce_database_identity(engine)
    await verify_schema(engine)
    logger.info("PostgreSQL connection and Alembic schema verified.")

    # 3. Qdrant
    try:
        qdrant = AsyncQdrantClient(
            url=f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}",
            check_compatibility=False,
        )
        exists = await qdrant.collection_exists(settings.QDRANT_COLLECTION)
        if not exists:
            logger.info(
                "Creating Qdrant collection '%s' with %d-dim dense cosine vectors...",
                settings.QDRANT_COLLECTION,
                settings.EMBEDDING_DIM,
            )
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

        info = await qdrant.get_collection(settings.QDRANT_COLLECTION)
        dense_cfg: Any = info.config.params.vectors.get("dense")  # type: ignore[union-attr]
        actual_dim = dense_cfg.size if dense_cfg else None
        if actual_dim != settings.EMBEDDING_DIM:
            raise RuntimeError(
                f"Qdrant vector dimension mismatch: collection '{settings.QDRANT_COLLECTION}' "
                f"has dense dim {actual_dim}, but config expects {settings.EMBEDDING_DIM}."
            )

        entity_exists = await qdrant.collection_exists(settings.QDRANT_ENTITY_COLLECTION)
        if not entity_exists:
            logger.info(
                "Creating Qdrant entity collection '%s' with %d-dim dense cosine vectors...",
                settings.QDRANT_ENTITY_COLLECTION,
                settings.EMBEDDING_DIM,
            )
            await qdrant.create_collection(
                collection_name=settings.QDRANT_ENTITY_COLLECTION,
                vectors_config=models.VectorParams(
                    size=settings.EMBEDDING_DIM,
                    distance=models.Distance.COSINE,
                ),
            )
        entity_info = await qdrant.get_collection(settings.QDRANT_ENTITY_COLLECTION)
        entity_dim = getattr(entity_info.config.params.vectors, "size", None)
        if entity_dim != settings.EMBEDDING_DIM:
            raise RuntimeError(
                f"Qdrant entity vector dimension mismatch: collection '{settings.QDRANT_ENTITY_COLLECTION}' "
                f"has dim {entity_dim}, but config expects {settings.EMBEDDING_DIM}."
            )

        await qdrant.close()
        logger.info(
            "Qdrant connection and collection schemas (%d-dim chunks, %d-dim entities) verified.",
            actual_dim,
            entity_dim,
        )
    except Exception as e:
        raise RuntimeError(
            f"Startup failed: Qdrant check failed at {settings.QDRANT_HOST}:{settings.QDRANT_PORT}: {e}"
        ) from e

    # 4. Neo4j
    try:
        driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            result = await session.run("RETURN 1 AS ping")
            record = await result.single()
            if not record or record["ping"] != 1:
                raise RuntimeError("Neo4j ping query did not return 1")
        await driver.close()
        logger.info("Neo4j connection and Cypher ping verified.")
    except Exception as e:
        raise RuntimeError(
            f"Startup failed: Neo4j is unreachable at {settings.NEO4J_URI}: {e}"
        ) from e

    # 5. Redis
    try:
        redis_client = aioredis.from_url(settings.redis_url)
        pong = await redis_client.ping()
        if not pong:
            raise RuntimeError("Redis ping returned False")
        await redis_client.aclose()
        logger.info("Redis connection and PING verified.")
    except Exception as e:
        raise RuntimeError(
            f"Startup failed: Redis is unreachable at {settings.REDIS_HOST}:{settings.REDIS_PORT}: {e}"
        ) from e

    logger.info("All live infrastructure checks PASSED.")
