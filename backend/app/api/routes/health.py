from fastapi import APIRouter, status
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    status: str = "ok"


class ReadinessResponse(BaseModel):
    status: str
    version: str
    environment: str
    configured_stores: dict[str, bool]


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
