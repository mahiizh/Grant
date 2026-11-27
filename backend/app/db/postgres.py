import asyncio
import hashlib
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload

from app.core.acl import ACLScope
from app.core.config import get_settings
from app.core.store_guard import assert_writable_stores
from app.db.models import Base, ChunkRecord, DocumentRecord
from app.db.outbox import OutboxEventType, OutboxService
from app.domain import (
    Chunk,
    Document,
    Provenance,
    SourceTier,
)

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_engine_loop: asyncio.AbstractEventLoop | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(db_url: str | None = None) -> AsyncEngine:
    global _engine, _engine_loop
    current_loop: asyncio.AbstractEventLoop | None = None
    with suppress(RuntimeError):
        current_loop = asyncio.get_running_loop()

    settings = get_settings()
    if db_url is None:
        assert_writable_stores(settings)

    if (
        _engine is None
        or db_url is not None
        or (_engine_loop is not None and current_loop is not None and current_loop != _engine_loop)
    ):
        url = db_url or settings.database_url
        # Adjust pool parameters based on SQLite vs Postgres vs test environment
        if "sqlite" in url or settings.APP_ENV == "test":
            from sqlalchemy.pool import NullPool

            engine = create_async_engine(url, echo=False, poolclass=NullPool)
        else:
            engine = create_async_engine(
                url,
                echo=False,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
            )
        if db_url is None:
            _engine = engine
            _engine_loop = current_loop
        return engine
    return _engine


def get_session_factory(engine: AsyncEngine | None = None) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    eng = engine or get_engine()
    if _session_factory is None or engine is not None or _session_factory.kw.get("bind") != eng:
        factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)
        if engine is None:
            _session_factory = factory
        return factory
    return _session_factory


async def init_db(engine: AsyncEngine | None = None) -> None:
    """Create every table directly from metadata (tests only).

    Production schema changes must go through Alembic (`make migrate`); see
    ``verify_schema`` for the startup guard.
    """
    eng = engine or get_engine()
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def redacted_database_url(db_url: str | None = None) -> str:
    """Return the resolved SQLAlchemy URL with the password hidden."""
    return make_url(db_url or get_settings().database_url).render_as_string(hide_password=True)


async def describe_database(engine: AsyncEngine | None = None) -> dict[str, Any]:
    """Return the physical server identity behind the configured DATABASE_URL.

    This is deliberately reported by the app, the ingestion CLI and the
    reconciler so a mixed native/Docker PostgreSQL setup is visible instead of
    silently writing to a different server.
    """
    eng = engine or get_engine()
    async with eng.connect() as conn:
        row = (
            (
                await conn.execute(
                    text(
                        "select current_database() as db, "
                        "current_user as user_name, "
                        "current_setting('data_directory') as data_directory, "
                        "coalesce(host(inet_server_addr()), 'local') as server_addr, "
                        "inet_server_port() as server_port"
                    )
                )
            )
            .mappings()
            .one()
        )
    return {
        "database_url": redacted_database_url(str(eng.url)),
        "db": row["db"],
        "user": row["user_name"],
        "data_directory": row["data_directory"],
        "server_addr": row["server_addr"],
        "server_port": row["server_port"],
    }


def database_identity_lines(info: dict[str, Any]) -> tuple[str, str]:
    """Render the two human-readable identity lines used by every entry point."""
    url_line = f"Resolved DATABASE_URL: {info['database_url']}"
    server_line = (
        f"PostgreSQL server: {info['server_addr']}:{info['server_port']} "
        f"| database={info['db']} | data_directory={info['data_directory']}"
    )
    return url_line, server_line


async def announce_database_identity(engine: AsyncEngine | None = None) -> dict[str, Any]:
    """Print and log the resolved DATABASE_URL and the server that answers it.

    Used by the app lifespan, the ingestion CLI and the reconciler so all three
    visibly agree on which PostgreSQL server they are writing to.
    """
    info = await describe_database(engine)
    url_line, server_line = database_identity_lines(info)
    print(url_line)
    print(server_line)
    logger.info("%s | %s", url_line, server_line)
    return info


async def verify_schema(engine: AsyncEngine | None = None) -> None:
    """Fail fast when Alembic migrations have not been applied."""
    eng = engine or get_engine()
    async with eng.connect() as conn:
        version_table = (
            await conn.execute(text("select to_regclass('public.alembic_version')"))
        ).scalar()
    if version_table is None:
        raise RuntimeError(
            "Database schema is not initialized: table 'alembic_version' is missing. "
            "Run `make migrate` (Alembic) before starting the app, ingestion, or reconciler."
        )


@asynccontextmanager
async def get_session(
    engine: AsyncEngine | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    """Context manager for managing an async database transaction."""
    factory = get_session_factory(engine)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for yielding database sessions."""
    async with get_session() as session:
        yield session


class DocumentRepository:
    """Repository handling CRUD operations and transactional outbox event staging."""

    @staticmethod
    def _parse_optional_datetime(value: Any) -> datetime | None:
        if not value or isinstance(value, datetime):
            return value if isinstance(value, datetime) else None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None

    @classmethod
    def _chunk_ingested_at(cls, record: ChunkRecord) -> datetime:
        """Restore a chunk's ingestion timestamp from its JSON metadata."""
        raw = (record.metadata_json or {}).get("ingested_at")
        return cls._parse_optional_datetime(raw) or datetime.now(UTC)

    @classmethod
    def _chunk_to_record(cls, chunk: Chunk) -> ChunkRecord:
        source_kind = str(chunk.metadata.get("source_kind", "document") or "document")
        url = chunk.metadata.get("url") or (
            chunk.provenance.source_uri if source_kind == "web" else None
        )
        metadata = dict(chunk.metadata)
        metadata.setdefault("ingested_at", chunk.ingested_at.isoformat())
        return ChunkRecord(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            chunk_index=chunk.index,
            text=chunk.text,
            tokens=chunk.tokens,
            owner_user_id=chunk.owner_user_id or chunk.acl_scope.owner_user_id,
            shared_scope=chunk.acl_scope.shared_scope,
            source_tier=int(chunk.provenance.tier),
            source_uri=chunk.provenance.source_uri,
            source_kind=source_kind,
            url=str(url) if url else None,
            fetched_at=cls._parse_optional_datetime(chunk.metadata.get("fetched_at")),
            provenance_confidence=chunk.provenance.confidence,
            provenance_verified=chunk.provenance.verified,
            metadata_json=metadata,
        )

    @staticmethod
    def _record_to_domain_chunk(record: ChunkRecord) -> Chunk:
        acl = ACLScope(
            owner_user_id=getattr(record, "owner_user_id", None),
            shared_scope=getattr(record, "shared_scope", None),
        )
        prov = Provenance(
            tier=SourceTier(record.source_tier),
            source_uri=record.source_uri,
            confidence=record.provenance_confidence,
            verified=record.provenance_verified,
        )
        metadata = dict(record.metadata_json or {})
        metadata.setdefault("source_kind", getattr(record, "source_kind", "document"))
        if getattr(record, "url", None):
            metadata.setdefault("url", record.url)
        if getattr(record, "fetched_at", None):
            metadata.setdefault("fetched_at", record.fetched_at.isoformat())
        return Chunk(
            chunk_id=record.chunk_id,
            doc_id=record.doc_id,
            index=record.chunk_index,
            text=record.text,
            tokens=record.tokens,
            owner_user_id=getattr(record, "owner_user_id", None),
            acl_scope=acl,
            ingested_at=DocumentRepository._chunk_ingested_at(record),
            provenance=prov,
            metadata=metadata,
        )

    @staticmethod
    def _record_to_domain_doc(record: DocumentRecord) -> Document:
        acl = ACLScope(
            owner_user_id=getattr(record, "owner_user_id", None),
            shared_scope=getattr(record, "shared_scope", None),
        )
        prov = Provenance(
            tier=SourceTier(record.source_tier),
            source_uri=record.source_uri,
            confidence=record.provenance_confidence,
            verified=record.provenance_verified,
        )
        domain_chunks = [
            DocumentRepository._record_to_domain_chunk(c)
            for c in sorted(record.chunks, key=lambda x: x.chunk_index)
        ]
        metadata = dict(record.metadata_json or {})
        metadata.setdefault("source_kind", getattr(record, "source_kind", "document"))
        if getattr(record, "url", None):
            metadata.setdefault("url", record.url)
        if getattr(record, "fetched_at", None):
            metadata.setdefault("fetched_at", record.fetched_at.isoformat())
        return Document(
            doc_id=record.doc_id,
            title=record.title,
            content=record.content,
            chunks=domain_chunks,
            owner_user_id=getattr(record, "owner_user_id", None),
            acl_scope=acl,
            ingested_at=record.ingested_at,
            provenance=prov,
            version=record.version,
            source_version=record.source_version,
            content_hash=record.content_hash,
            metadata=metadata,
        )

    @staticmethod
    def _effective_content_hash(document: Document) -> str:
        """Return the declared content hash, or derive one from the document body."""
        if document.content_hash:
            return document.content_hash
        return hashlib.sha256(document.content.encode("utf-8")).hexdigest()

    @staticmethod
    def _acl_scope_payload(
        owner_user_id: str | None,
        shared_scope: str | None,
    ) -> dict[str, Any]:
        """Build the serialized owner/shared ACL stored in downstream payloads."""
        return {
            "owner_user_id": owner_user_id or None,
            "shared_scope": shared_scope or None,
        }

    @classmethod
    def _document_event_payload(
        cls,
        document: Document,
        *,
        chunk_count: int,
    ) -> dict[str, Any]:
        """Shared payload for ``DOCUMENT_INGESTED`` and repair re-queues."""
        source_kind = str(document.metadata.get("source_kind", "document") or "document")
        url = document.metadata.get("url") or (
            document.provenance.source_uri if source_kind == "web" else None
        )
        fetched_at = cls._parse_optional_datetime(document.metadata.get("fetched_at"))
        owner = document.owner_user_id or document.acl_scope.owner_user_id
        return {
            "doc_id": document.doc_id,
            "title": document.title,
            "version": document.version,
            "chunk_count": chunk_count,
            "owner_user_id": owner,
            "shared_scope": document.acl_scope.shared_scope,
            "acl_scope": cls._acl_scope_payload(owner, document.acl_scope.shared_scope),
            "source_uri": document.provenance.source_uri,
            "source_kind": source_kind,
            "url": str(url) if url else None,
            "fetched_at": fetched_at.isoformat() if fetched_at else None,
            "content_hash": cls._effective_content_hash(document),
        }

    @classmethod
    def _chunk_event_payload(cls, chunk: Chunk, document: Document) -> dict[str, Any]:
        """Shared payload for ``CHUNK_UPSERTED`` and repair re-queues.

        Qdrant stores everything graph retrieval needs: chunk text plus document
        identity, owner ACL, source kind, title, and URL. The document checksum
        lets the reconciler detect stale points without a second Postgres lookup.
        """
        owner = (
            chunk.owner_user_id
            or document.owner_user_id
            or chunk.acl_scope.owner_user_id
        )
        source_kind = str(chunk.metadata.get("source_kind", "document") or "document")
        return {
            "chunk_id": chunk.chunk_id,
            "doc_id": chunk.doc_id,
            "index": chunk.index,
            "text": chunk.text,
            "tokens": chunk.tokens,
            "owner_user_id": owner,
            "acl_scope": chunk.acl_scope.model_dump(mode="json"),
            "ingested_at": chunk.ingested_at.isoformat(),
            "source_tier": int(chunk.provenance.tier),
            "source_kind": source_kind,
            "source_uri": chunk.provenance.source_uri,
            "title": document.title,
            "url": chunk.metadata.get("url"),
            "fetched_at": chunk.metadata.get("fetched_at"),
            "doc_checksum": cls._effective_content_hash(document),
            "entities": chunk.metadata.get("entities", []),
            "relations": chunk.metadata.get("relations", []),
        }

    @staticmethod
    def _index_fingerprint(document: Document) -> tuple[Any, ...]:
        """Fields that change downstream index state when they change.

        Chunk text is derived from content and ACL payloads are derived from the
        document scope, so an unchanged fingerprint means the existing chunks
        and index records are still valid.
        """
        return (
            DocumentRepository._effective_content_hash(document),
            document.owner_user_id or document.acl_scope.owner_user_id,
            document.acl_scope.shared_scope,
        )

    @classmethod
    async def save_document(
        cls,
        session: AsyncSession,
        document: Document,
    ) -> DocumentRecord:
        """Atomically persist a document, replace chunks, and stage outbox events.

        Re-saving a document whose content and index-relevant ACL fields are
        unchanged is a no-op for chunks and downstream indexing: no
        ``DOCUMENT_INGESTED``, ``CHUNK_UPSERTED``, or ``CACHE_INVALIDATED`` events
        are staged, so retries and duplicate ingest jobs cannot flood the outbox
        or re-embed identical chunks.
        """
        stmt = (
            select(DocumentRecord)
            .options(selectinload(DocumentRecord.chunks))
            .where(DocumentRecord.doc_id == document.doc_id)
        )
        result = await session.execute(stmt)
        existing_doc = result.scalar_one_or_none()
        source_kind = str(document.metadata.get("source_kind", "document") or "document")
        url = document.metadata.get("url") or (
            document.provenance.source_uri if source_kind == "web" else None
        )
        fetched_at = cls._parse_optional_datetime(document.metadata.get("fetched_at"))

        if existing_doc is not None:
            existing_fingerprint = (
                existing_doc.content_hash
                or hashlib.sha256(existing_doc.content.encode("utf-8")).hexdigest(),
                getattr(existing_doc, "owner_user_id", None),
                getattr(existing_doc, "shared_scope", None),
            )
            if existing_fingerprint == cls._index_fingerprint(document):
                # Content and index-relevant metadata are unchanged: keep chunks
                # and outbox state untouched, but still persist display-only
                # fields such as title, version, and metadata.
                existing_doc.title = document.title
                existing_doc.version = document.version
                existing_doc.owner_user_id = document.owner_user_id or document.acl_scope.owner_user_id
                existing_doc.shared_scope = document.acl_scope.shared_scope
                existing_doc.content_hash = cls._effective_content_hash(document)
                existing_doc.metadata_json = document.metadata
                existing_doc.source_version = document.source_version
                existing_doc.source_tier = int(document.provenance.tier)
                existing_doc.source_uri = document.provenance.source_uri
                existing_doc.source_kind = source_kind
                existing_doc.url = str(url) if url else None
                existing_doc.fetched_at = fetched_at
                existing_doc.provenance_confidence = document.provenance.confidence
                existing_doc.provenance_verified = document.provenance.verified
                logger.debug("Document %s unchanged; skipping re-index", document.doc_id)
                return existing_doc

        if existing_doc is None:
            doc_record = DocumentRecord(
                doc_id=document.doc_id,
                title=document.title,
                content=document.content,
                version=document.version,
                content_hash=cls._effective_content_hash(document),
                owner_user_id=document.owner_user_id or document.acl_scope.owner_user_id,
                shared_scope=document.acl_scope.shared_scope,
                ingested_at=document.ingested_at,
                source_version=document.source_version,
                source_tier=int(document.provenance.tier),
                source_uri=document.provenance.source_uri,
                source_kind=source_kind,
                url=str(url) if url else None,
                fetched_at=fetched_at,
                provenance_confidence=document.provenance.confidence,
                provenance_verified=document.provenance.verified,
                metadata_json=document.metadata,
            )
            session.add(doc_record)
        else:
            doc_record = existing_doc
            doc_record.title = document.title
            doc_record.content = document.content
            doc_record.version = document.version
            doc_record.owner_user_id = document.owner_user_id or document.acl_scope.owner_user_id
            doc_record.content_hash = cls._effective_content_hash(document)
            doc_record.shared_scope = document.acl_scope.shared_scope
            doc_record.source_version = document.source_version
            doc_record.source_tier = int(document.provenance.tier)
            doc_record.source_uri = document.provenance.source_uri
            doc_record.source_kind = source_kind
            doc_record.url = str(url) if url else None
            doc_record.fetched_at = fetched_at
            doc_record.provenance_confidence = document.provenance.confidence
            doc_record.provenance_verified = document.provenance.verified
            doc_record.metadata_json = document.metadata

            # Clear old chunks for clean replacement. Mentions are managed by the
            # ingestion pipeline in explicit order: save doc -> delete old mentions -> insert new.
            await session.execute(delete(ChunkRecord).where(ChunkRecord.doc_id == document.doc_id))

        # Insert new chunks
        for chunk in document.chunks:
            chunk_rec = cls._chunk_to_record(chunk)
            session.add(chunk_rec)

        # Stage DOCUMENT_INGESTED outbox event
        doc_payload = cls._document_event_payload(document, chunk_count=len(document.chunks))
        OutboxService.stage_event(
            session=session,
            event_type=OutboxEventType.DOCUMENT_INGESTED,
            aggregate_type="document",
            aggregate_id=document.doc_id,
            payload=doc_payload,
        )

        # Stage CHUNK_UPSERTED outbox events for downstream Qdrant / Neo4j indexers
        for chunk in document.chunks:
            chunk_payload = cls._chunk_event_payload(chunk, document)
            OutboxService.stage_event(
                session=session,
                event_type=OutboxEventType.CHUNK_UPSERTED,
                aggregate_type="chunk",
                aggregate_id=chunk.chunk_id,
                payload=chunk_payload,
            )

        # Stage the version bump last: the worker sees indexed chunks before it
        # invalidates answers produced by the previous index version.
        OutboxService.stage_event(
            session=session,
            event_type=OutboxEventType.CACHE_INVALIDATED,
            aggregate_type="cache",
            aggregate_id=document.doc_id,
            payload={
                "doc_id": document.doc_id,
                "reason": (
                    "document_content_changed" if existing_doc is not None else "document_indexed"
                ),
                "owner_user_id": document.owner_user_id or document.acl_scope.owner_user_id,
                "shared_scope": document.acl_scope.shared_scope,
            },
        )

        return doc_record

    @classmethod
    async def get_document(
        cls,
        session: AsyncSession,
        doc_id: str,
    ) -> Document | None:
        """Fetch document and its chunks by ID, reconstructed into a Domain model."""
        stmt = (
            select(DocumentRecord)
            .options(selectinload(DocumentRecord.chunks))
            .where(DocumentRecord.doc_id == doc_id)
        )
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return cls._record_to_domain_doc(record)

    @classmethod
    async def delete_document(
        cls,
        session: AsyncSession,
        doc_id: str,
    ) -> bool:
        """Delete document and stage deletion and cache invalidation outbox events."""
        stmt = select(DocumentRecord).where(DocumentRecord.doc_id == doc_id)
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            return False

        # Stage DOCUMENT_DELETED outbox event
        owner_user_id = record.owner_user_id
        OutboxService.stage_event(
            session=session,
            event_type=OutboxEventType.DOCUMENT_DELETED,
            aggregate_type="document",
            aggregate_id=doc_id,
            payload={"doc_id": doc_id, "owner_user_id": owner_user_id},
        )

        # Stage CACHE_INVALIDATED outbox event after the downstream delete.
        OutboxService.stage_event(
            session=session,
            event_type=OutboxEventType.CACHE_INVALIDATED,
            aggregate_type="cache",
            aggregate_id=doc_id,
            payload={
                "doc_id": doc_id,
                "reason": "document_deletion",
                "owner_user_id": owner_user_id,
                "shared_scope": record.shared_scope,
            },
        )

        await session.delete(record)
        return True
