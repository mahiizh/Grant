import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    documents,
    graph,
    health,
    metrics,
    query,
    threads,
)
from app.api.routes import (
    settings as settings_routes,
)
from app.core.config import get_settings
from app.core.lifecycle import verify_infrastructure_live
from app.core.store_guard import (
    DEV_WRITE_TOKEN_HEADER,
    WRITE_METHODS,
    WRITE_REFUSAL,
    http_write_violations,
)
from app.observability.tracer import setup_telemetry
from app.runtime import shutdown_models, startup_models


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Lifespan startup: verify real infrastructure & keys in live mode, init DB schema
    await verify_infrastructure_live()
    # Register the Langfuse OTLP tracer once; a no-op when keys are unset.
    setup_telemetry()
    # Build and warm local models once; all inference now reuses this bundle.
    await startup_models()
    yield
    # Lifespan shutdown
    shutdown_models()


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

    @app.middleware("http")
    async def guard_store_writes(request: Request, call_next: Any) -> Any:
        """Block HTTP writes to developer stores unless explicitly authorized."""
        if request.method in WRITE_METHODS:
            violations = http_write_violations(
                get_settings(), request.headers.get(DEV_WRITE_TOKEN_HEADER)
            )
            if violations:
                return JSONResponse(
                    status_code=423,
                    content={"detail": f"{WRITE_REFUSAL}: " + "; ".join(violations)},
                )
        return await call_next(request)

    # Register Routers under single API prefix (/api/v1)
    api_routers = [
        health.router,
        query.router,
        graph.router,
        documents.router,
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
