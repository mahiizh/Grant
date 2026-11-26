"""Upload enqueues a job; the worker owns parsing and indexing."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers, UploadFile

from app.api.routes import documents as documents_route
from app.core.auth import AuthenticatedUser
from app.core.config import get_settings
from app.db.models import Base, IngestionJobRecord
from app.ingestion.pipeline import IngestionSummary
from app.workers import ingestion_worker as worker_module


class JobDB:
    """In-memory SQLite schema created inside the active event loop."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.monkeypatch = monkeypatch
        self.factory: async_sessionmaker[AsyncSession] | None = None

    async def setup(self) -> async_sessionmaker[AsyncSession]:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(
            bind=engine, expire_on_commit=False, class_=AsyncSession
        )

        @asynccontextmanager
        async def fake_get_session(*_args: Any, **_kwargs: Any):
            assert self.factory is not None
            async with self.factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        self.monkeypatch.setattr(documents_route, "get_session", fake_get_session)
        self.monkeypatch.setattr(worker_module, "get_session", fake_get_session)
        return self.factory


@pytest.fixture
def job_db(monkeypatch: pytest.MonkeyPatch) -> JobDB:
    return JobDB(monkeypatch)


def alice() -> AuthenticatedUser:
    settings = get_settings()
    return AuthenticatedUser("alice", settings.DEV_USERS["alice"])


@pytest.mark.anyio
async def test_upload_writes_file_and_job_without_ingesting(
    monkeypatch: pytest.MonkeyPatch,
    job_db: JobDB,
) -> None:
    db = await job_db.setup()

    def forbidden_pipeline(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("upload must not call IngestionPipeline")

    monkeypatch.setattr(documents_route, "IngestionPipeline", forbidden_pipeline, raising=False)

    upload = UploadFile(
        file=BytesIO(b"# Worker job spec\n\nThe worker handles this document."),
        filename="worker_job_spec.md",
        headers=Headers({"content-type": "text/markdown"}),
    )
    response = await documents_route.upload_document(file=upload, current_user=alice())

    assert response.status == "queued"
    assert response.job_id.startswith("job-")
    assert response.document_id.startswith("doc_")

    async with db() as session:
        job = (await session.execute(select(IngestionJobRecord))).scalar_one()
    assert job.status == "queued"
    assert job.content.startswith(b"# Worker job spec")
    assert job.owner_user_id == "usr_alice_01"


@pytest.mark.anyio
async def test_status_reports_job_progress_and_ingest_time(
    job_db: JobDB,
) -> None:
    db = await job_db.setup()
    async with db() as session:
        session.add(
            IngestionJobRecord(
                job_id="job-status-1",
                document_id="doc_status_1",
                owner_user_id="usr_alice_01",
                file_name="status.md",
                content=b"# Status",
                status="completed",
                active_step="complete",
                step_index=6,
                entity_count=4,
                relation_count=2,
                extraction_status="completed",
                created_at=datetime.now(UTC) - timedelta(seconds=3),
                completed_at=datetime.now(UTC),
            )
        )
        await session.commit()

    status = await documents_route.get_document_status("doc_status_1", current_user=alice())

    assert status.status == "completed"
    assert status.job_id == "job-status-1"
    assert status.entities == 4
    assert status.ingest_ms is not None and status.ingest_ms >= 2900


@pytest.mark.anyio
async def test_worker_claims_and_completes_job(
    monkeypatch: pytest.MonkeyPatch,
    job_db: JobDB,
) -> None:
    db = await job_db.setup()
    calls: dict[str, int] = {"ingest": 0, "drain": 0}

    class FakePipeline:
        @classmethod
        async def ingest_text(cls, **_kwargs: Any) -> IngestionSummary:
            calls["ingest"] += 1
            return IngestionSummary(
                doc_id="doc_worker_done",
                title="Worker job spec",
                chunk_count=2,
                entity_count=7,
                relation_count=3,
            )

    class FakeOutboxWorker:
        async def drain(self) -> int:
            calls["drain"] += 1
            return 1

    monkeypatch.setattr(worker_module, "IngestionPipeline", FakePipeline)
    monkeypatch.setattr(worker_module, "OutboxWorker", FakeOutboxWorker)

    async with db() as session:
        session.add(
            IngestionJobRecord(
                job_id="job-worker-1",
                document_id="doc_worker_1",
                owner_user_id="usr_alice_01",
                file_name="worker.md",
                content=b"# Worker",
                status="queued",
                active_step="queued",
                step_index=0,
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()

    claimed = await worker_module.claim_next_job()
    assert claimed is not None and claimed.job_id == "job-worker-1"
    assert await worker_module.claim_next_job() is None
    assert await worker_module.process_job(claimed)

    async with db() as session:
        job = await session.get(IngestionJobRecord, "job-worker-1")
    assert job is not None
    assert job.status == "completed"
    assert job.document_id == "doc_worker_done"
    assert job.entity_count == 7
    assert job.relation_count == 3
    assert calls == {"ingest": 1, "drain": 1}
