from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.acl import ACLScope
from app.db.models import Base
from app.db.outbox import OutboxEventType, OutboxService, OutboxStatus
from app.db.postgres import DocumentRepository
from app.domain import (
    Chunk,
    Document,
    Provenance,
    TemporalBounds,
)


@pytest.fixture
async def test_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated, in-memory SQLite database session for unit tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.anyio
async def test_outbox_event_staging_and_lifecycle(test_session: AsyncSession) -> None:
    # 1. Stage an event
    event = OutboxService.stage_event(
        session=test_session,
        event_type=OutboxEventType.DOCUMENT_INGESTED,
        aggregate_type="document",
        aggregate_id="doc_123",
        payload={"title": "Test Doc"},
    )
    await test_session.flush()

    assert event.event_id.startswith("evt_")
    assert event.status == OutboxStatus.PENDING.value
    assert event.retry_count == 0

    # 2. Fetch pending events
    pending = await OutboxService.fetch_pending_events(session=test_session, limit=10)
    assert len(pending) == 1
    assert pending[0].event_id == event.event_id

    # 3. Mark processed
    processed = await OutboxService.mark_processed(
        session=test_session,
        event_id=event.event_id,
    )
    await test_session.flush()

    assert processed is not None
    assert processed.status == OutboxStatus.PROCESSED.value
    assert processed.processed_at is not None

    # Verify no more pending events
    remaining = await OutboxService.fetch_pending_events(session=test_session, limit=10)
    assert len(remaining) == 0


@pytest.mark.anyio
async def test_outbox_retry_and_dead_letter(test_session: AsyncSession) -> None:
    event = OutboxService.stage_event(
        session=test_session,
        event_type=OutboxEventType.CHUNK_UPSERTED,
        aggregate_type="chunk",
        aggregate_id="chk_001",
        payload={"text": "Faulty payload"},
        max_retries=2,
    )
    await test_session.flush()

    # First failure -> retryable FAILED
    failed_1 = await OutboxService.mark_failed(
        session=test_session,
        event_id=event.event_id,
        error_message="Connection timeout to Qdrant",
    )
    assert failed_1 is not None
    assert failed_1.status == OutboxStatus.FAILED.value
    assert failed_1.retry_count == 1
    assert failed_1.last_error == "Connection timeout to Qdrant"

    # Still returned by fetch_pending_events because retry_count < max_retries
    retryable = await OutboxService.fetch_pending_events(session=test_session, limit=10)
    assert len(retryable) == 1

    # Second failure -> transitions to DEAD_LETTER (DLQ)
    failed_2 = await OutboxService.mark_failed(
        session=test_session,
        event_id=event.event_id,
        error_message="Persistent deserialization error",
    )
    assert failed_2 is not None
    assert failed_2.status == OutboxStatus.DEAD_LETTER.value
    assert failed_2.retry_count == 2

    # Dead letter events are not returned by standard pending fetch
    remaining = await OutboxService.fetch_pending_events(session=test_session, limit=10)
    assert len(remaining) == 0

    # Found in DLQ inspection
    dlq = await OutboxService.get_dead_letter_events(session=test_session, limit=10)
    assert len(dlq) == 1
    assert dlq[0].event_id == event.event_id


@pytest.mark.anyio
async def test_document_repository_save_and_retrieve(test_session: AsyncSession) -> None:
    now = datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC)
    temporal = TemporalBounds.current(valid_from=now)
    prov = Provenance.from_document(source_uri="corpus/rfc_001.md")
    acl = ACLScope.restricted(allowed_roles={"platform_engineer"}, tenant_id="acme")

    chunk_1 = Chunk(
        chunk_id="chk_rfc001_0001",
        doc_id="doc_rfc001",
        index=0,
        text="Section 1: Outbox pattern",
        tokens=5,
        acl_scope=acl,
        temporal=temporal,
        provenance=prov,
    )
    chunk_2 = Chunk(
        chunk_id="chk_rfc001_0002",
        doc_id="doc_rfc001",
        index=1,
        text="Section 2: Qdrant vectors",
        tokens=5,
        acl_scope=acl,
        temporal=temporal,
        provenance=prov,
    )
    doc = Document(
        doc_id="doc_rfc001",
        title="RFC 001 Storage",
        content="Section 1: Outbox pattern\nSection 2: Qdrant vectors",
        chunks=[chunk_1, chunk_2],
        acl_scope=acl,
        temporal=temporal,
        provenance=prov,
        version=1,
    )

    # Save document atomically
    await DocumentRepository.save_document(session=test_session, document=doc)
    await test_session.flush()

    # Verify outbox events staged (1 document + 2 chunks = 3 events)
    pending_events = await OutboxService.fetch_pending_events(session=test_session, limit=10)
    assert len(pending_events) == 3
    event_types = {e.event_type for e in pending_events}
    assert OutboxEventType.DOCUMENT_INGESTED.value in event_types
    assert OutboxEventType.CHUNK_UPSERTED.value in event_types

    # Retrieve and verify round-trip domain mapping
    retrieved = await DocumentRepository.get_document(session=test_session, doc_id="doc_rfc001")
    assert retrieved is not None
    assert retrieved.doc_id == "doc_rfc001"
    assert retrieved.title == "RFC 001 Storage"
    assert retrieved.acl_scope.tenant_id == "acme"
    assert not retrieved.acl_scope.is_public
    assert "platform_engineer" in retrieved.acl_scope.allowed_roles
    assert len(retrieved.chunks) == 2
    assert retrieved.chunks[0].chunk_id == "chk_rfc001_0001"
    assert retrieved.chunks[1].chunk_id == "chk_rfc001_0002"


@pytest.mark.anyio
async def test_document_repository_delete_and_invalidation(test_session: AsyncSession) -> None:
    now = datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC)
    temporal = TemporalBounds.current(valid_from=now)
    prov = Provenance.from_document(source_uri="corpus/postmortem.md")
    acl = ACLScope.public()

    chunk = Chunk(
        chunk_id="chk_postmortem_01",
        doc_id="doc_postmortem",
        index=0,
        text="Sev-1 Postmortem",
        tokens=3,
        acl_scope=acl,
        temporal=temporal,
        provenance=prov,
    )
    doc = Document(
        doc_id="doc_postmortem",
        title="Incident 04 Postmortem",
        content="Sev-1 Postmortem",
        chunks=[chunk],
        acl_scope=acl,
        temporal=temporal,
        provenance=prov,
    )

    await DocumentRepository.save_document(session=test_session, document=doc)
    await test_session.flush()

    # Clear pending events from creation
    events = await OutboxService.fetch_pending_events(session=test_session, limit=10)
    for e in events:
        await OutboxService.mark_processed(session=test_session, event_id=e.event_id)
    await test_session.flush()

    # Delete the document
    deleted = await DocumentRepository.delete_document(
        session=test_session, doc_id="doc_postmortem"
    )
    assert deleted is True

    # Confirm it's gone
    retrieved = await DocumentRepository.get_document(session=test_session, doc_id="doc_postmortem")
    assert retrieved is None

    # Verify deletion and cache invalidation outbox events were staged
    deletion_events = await OutboxService.fetch_pending_events(session=test_session, limit=10)
    assert len(deletion_events) == 2
    del_types = {e.event_type for e in deletion_events}
    assert OutboxEventType.DOCUMENT_DELETED.value in del_types
    assert OutboxEventType.CACHE_INVALIDATED.value in del_types
