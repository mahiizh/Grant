import time
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter
from neo4j import AsyncGraphDatabase
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text

from app.api.schemas.settings import SettingsResponse, StoreStatus, UpdateSettingsRequest
from app.core.config import get_settings
from app.db.postgres import get_engine

router = APIRouter(prefix="/settings", tags=["settings"])

_settings_state: dict[str, Any] = {"canvas_theme": "dark"}


@router.get("", response_model=SettingsResponse)
async def get_system_settings() -> SettingsResponse:
    """Retrieve system settings, ACL scopes, store health, and defaults."""
    settings = get_settings()

    # Shared scopes are the only requestable non-owner boundaries.
    all_scopes: set[str] = set()
    for user_info in settings.DEV_USERS.values():
        all_scopes.update(user_info.get("shared_scopes", []))

    stores: dict[str, StoreStatus] = {}

    # 1. Postgres
    started = time.perf_counter()
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency = (time.perf_counter() - started) * 1000
        stores["postgres"] = StoreStatus(
            status="healthy", latency_ms=round(latency, 2), configured=True
        )
    except Exception:
        stores["postgres"] = StoreStatus(status="unhealthy", latency_ms=0.0, configured=True)

    # 2. Qdrant
    started = time.perf_counter()
    try:
        qdrant = AsyncQdrantClient(
            url=f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}", check_compatibility=False
        )
        await qdrant.get_collections()
        await qdrant.close()
        latency = (time.perf_counter() - started) * 1000
        stores["qdrant"] = StoreStatus(
            status="healthy", latency_ms=round(latency, 2), configured=True
        )
    except Exception:
        stores["qdrant"] = StoreStatus(status="unhealthy", latency_ms=0.0, configured=True)

    # 3. Neo4j
    started = time.perf_counter()
    try:
        driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
        async with driver.session(database=settings.NEO4J_DATABASE) as s:
            await s.run("RETURN 1")
        await driver.close()
        latency = (time.perf_counter() - started) * 1000
        stores["neo4j"] = StoreStatus(
            status="healthy", latency_ms=round(latency, 2), configured=True
        )
    except Exception:
        stores["neo4j"] = StoreStatus(status="unhealthy", latency_ms=0.0, configured=True)

    # 4. Redis
    started = time.perf_counter()
    try:
        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        latency = (time.perf_counter() - started) * 1000
        stores["redis"] = StoreStatus(
            status="healthy", latency_ms=round(latency, 2), configured=True
        )
    except Exception:
        stores["redis"] = StoreStatus(status="unhealthy", latency_ms=0.0, configured=True)

    return SettingsResponse(
        shared_scopes=sorted(all_scopes),
        canvas_theme=str(_settings_state["canvas_theme"]),
        stores=stores,
    )


@router.patch("", response_model=SettingsResponse)
async def update_system_settings(
    request: UpdateSettingsRequest,
) -> SettingsResponse:
    """Update UI defaults. Shared scopes are credentials, not editable settings."""
    if request.canvas_theme is not None:
        _settings_state["canvas_theme"] = request.canvas_theme

    return await get_system_settings()
