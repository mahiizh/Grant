import asyncio
import time

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Response, status
from neo4j import AsyncGraphDatabase
from pydantic import BaseModel
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db.models import OutboxEventRecord
from app.db.postgres import get_engine, get_session

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    status: str = "ok"


class ReadinessResponse(BaseModel):
    status: str
    version: str
    environment: str
    configured_stores: dict[str, bool]


class ComponentHealth(BaseModel):
    status: str = "healthy"
    latency_ms: float = 1.0
    error: str | None = None


class SystemHealthResponse(BaseModel):
    status: str = "ok"
    version: str
    environment: str
    components: dict[str, ComponentHealth]
    outbox_lag: int = 0


async def check_postgres() -> ComponentHealth:
    start = time.perf_counter()
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency = round((time.perf_counter() - start) * 1000, 2)
        return ComponentHealth(status="healthy", latency_ms=latency)
    except Exception as e:
        return ComponentHealth(status="unhealthy", latency_ms=0.0, error=str(e))


async def check_qdrant() -> ComponentHealth:
    settings = get_settings()
    start = time.perf_counter()
    try:
        host = "127.0.0.1" if settings.QDRANT_HOST == "localhost" else settings.QDRANT_HOST
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"http://{host}:{settings.QDRANT_PORT}/readyz")
            if resp.status_code == 200:
                latency = round((time.perf_counter() - start) * 1000, 2)
                return ComponentHealth(status="healthy", latency_ms=latency)
            return ComponentHealth(
                status="unhealthy", latency_ms=0.0, error=f"HTTP {resp.status_code}"
            )
    except Exception as e:
        return ComponentHealth(status="unhealthy", latency_ms=0.0, error=str(e))


async def check_neo4j() -> ComponentHealth:
    settings = get_settings()
    start = time.perf_counter()
    try:
        driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        async with driver.session() as session:
            res = await session.run("RETURN 1 AS ping")
            record = await res.single()
            if not record or record["ping"] != 1:
                return ComponentHealth(
                    status="unhealthy", latency_ms=0.0, error="Invalid ping result"
                )
        await driver.close()
        latency = round((time.perf_counter() - start) * 1000, 2)
        return ComponentHealth(status="healthy", latency_ms=latency)
    except Exception as e:
        return ComponentHealth(status="unhealthy", latency_ms=0.0, error=str(e))


async def check_redis() -> ComponentHealth:
    settings = get_settings()
    start = time.perf_counter()
    try:
        r = aioredis.from_url(settings.redis_url)
        pong = await r.ping()
        await r.aclose()
        if pong:
            latency = round((time.perf_counter() - start) * 1000, 2)
            return ComponentHealth(status="healthy", latency_ms=latency)
        return ComponentHealth(status="unhealthy", latency_ms=0.0, error="Ping failed")
    except Exception as e:
        return ComponentHealth(status="unhealthy", latency_ms=0.0, error=str(e))


async def get_outbox_lag() -> int:
    try:
        async with get_session() as session:
            stmt = select(func.count(OutboxEventRecord.event_id)).where(
                OutboxEventRecord.status == "PENDING"
            )
            res = await session.execute(stmt)
            return int(res.scalar() or 0)
    except Exception:
        return 0


@router.get("", response_model=SystemHealthResponse)
@router.get("/", response_model=SystemHealthResponse)
async def system_health(response: Response) -> SystemHealthResponse:
    settings = get_settings()

    pg_h, qd_h, neo_h, rd_h, lag = await asyncio.gather(
        check_postgres(),
        check_qdrant(),
        check_neo4j(),
        check_redis(),
        get_outbox_lag(),
    )

    all_healthy = all(c.status == "healthy" for c in (pg_h, qd_h, neo_h, rd_h))

    if not all_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        overall = "degraded"
    else:
        response.status_code = status.HTTP_200_OK
        overall = "ok"

    return SystemHealthResponse(
        status=overall,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        components={
            "postgres": pg_h,
            "qdrant": qd_h,
            "neo4j": neo_h,
            "redis": rd_h,
            "outbox": ComponentHealth(
                status="healthy" if lag < 100 else "warning",
                latency_ms=float(lag),
            ),
        },
        outbox_lag=lag,
    )


@router.get("/live", response_model=LivenessResponse, status_code=status.HTTP_200_OK)
def liveness() -> LivenessResponse:
    return LivenessResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse, status_code=status.HTTP_200_OK)
def readiness() -> ReadinessResponse:
    settings = get_settings()
    return ReadinessResponse(
        status="ok",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        configured_stores={
            "postgres": bool(settings.POSTGRES_HOST),
            "qdrant": bool(settings.QDRANT_HOST),
            "neo4j": bool(settings.NEO4J_URI),
            "redis": bool(settings.REDIS_HOST),
        },
    )
