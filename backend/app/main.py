import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    cache,
    documents,
    evals,
    experiments,
    graph,
    health,
    metrics,
    query,
    retrieval,
    threads,
    traces,
)
from app.api.routes import (
    settings as settings_routes,
)
from app.core.config import get_settings
from app.core.lifecycle import verify_infrastructure_live


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Lifespan startup: verify real infrastructure & keys in live mode, init DB schema
    await verify_infrastructure_live()
    yield
    # Lifespan shutdown


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.DEBUG else ["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register Routers under single API prefix (/api/v1)
    api_routers = [
        health.router,
        query.router,
        graph.router,
        documents.router,
        traces.router,
        retrieval.router,
        cache.router,
        evals.router,
        experiments.router,
        metrics.router,
        settings_routes.router,
        threads.router,
    ]

    for router in api_routers:
        app.include_router(router, prefix=settings.API_V1_PREFIX)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "status": "online",
            "docs": "/docs" if settings.DEBUG else "disabled",
        }

    return app


app = create_app()
