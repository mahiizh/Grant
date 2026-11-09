import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
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
from app.db.models import Base, ChunkRecord, DocumentRecord
from app.db.outbox import OutboxEventType, OutboxService
from app.domain import (
    Chunk,
    Document,
    Provenance,
    SourceTier,
    TemporalBounds,
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

    if (
        _engine is None
        or db_url is not None
        or (_engine_loop is not None and current_loop is not None and current_loop != _engine_loop)
    ):
        url = db_url or get_settings().database_url
        # Adjust pool parameters based on SQLite vs Postgres vs test environment
        if "sqlite" in url or get_settings().APP_ENV == "test":
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
    def _chunk_to_record(chunk: Chunk) -> ChunkRecord:
        return ChunkRecord(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            chunk_index=chunk.index,
            text=chunk.text,
            tokens=chunk.tokens,
            acl_tenant_id=chunk.acl_scope.tenant_id,
            acl_allowed_roles=list(chunk.acl_scope.allowed_roles),
            acl_allowed_groups=list(chunk.acl_scope.allowed_groups),
            acl_is_public=chunk.acl_scope.is_public,
            valid_from=chunk.temporal.valid_from,
            valid_to=chunk.temporal.valid_to,
            source_tier=int(chunk.provenance.tier),
            source_uri=chunk.provenance.source_uri,
            provenance_confidence=chunk.provenance.confidence,
            provenance_verified=chunk.provenance.verified,
            metadata_json=chunk.metadata,
        )

    @staticmethod
    def _record_to_domain_chunk(record: ChunkRecord) -> Chunk:
        acl = ACLScope(
            tenant_id=record.acl_tenant_id,
            allowed_roles=frozenset(record.acl_allowed_roles or []),
            allowed_groups=frozenset(record.acl_allowed_groups or []),
            is_public=record.acl_is_public,
        )
        temporal = TemporalBounds(
            valid_from=record.valid_from,
            valid_to=record.valid_to,
        )
        prov = Provenance(
            tier=SourceTier(record.source_tier),
            source_uri=record.source_uri,
            confidence=record.provenance_confidence,
            verified=record.provenance_verified,
        )
        return Chunk(
            chunk_id=record.chunk_id,
            doc_id=record.doc_id,
            index=record.chunk_index,
            text=record.text,
            tokens=record.tokens,
            acl_scope=acl,
            temporal=temporal,
            provenance=prov,
            metadata=record.metadata_json or {},
        )

    @staticmethod
    def _record_to_domain_doc(record: DocumentRecord) -> Document:
        acl = ACLScope(
            tenant_id=record.acl_tenant_id,
            allowed_roles=frozenset(record.acl_allowed_roles or []),
            allowed_groups=frozenset(record.acl_allowed_groups or []),
            is_public=record.acl_is_public,
        )
        temporal = TemporalBounds(
            valid_from=record.valid_from,
            valid_to=record.valid_to,
            ingested_at=record.ingested_at,
            source_version=record.source_version,
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
        return Document(
            doc_id=record.doc_id,
            title=record.title,
            content=record.content,
            chunks=domain_chunks,
            acl_scope=acl,
            temporal=temporal,
            provenance=prov,
            version=record.version,
            content_hash=record.content_hash,
            metadata=record.metadata_json or {},
        )

    @classmethod
    async def save_document(
        cls,
        session: AsyncSession,
        document: Document,
    ) -> DocumentRecord:
        """Atomically persist a document, replace chunks, and stage outbox events."""
        stmt = (
            select(DocumentRecord)
            .options(selectinload(DocumentRecord.chunks))
            .where(DocumentRecord.doc_id == document.doc_id)
        )
        result = await session.execute(stmt)
        existing_doc = result.scalar_one_or_none()

        if existing_doc is None:
            doc_record = DocumentRecord(
                doc_id=document.doc_id,
                title=document.title,
                content=document.content,
                version=document.version,
                content_hash=document.content_hash,
                acl_tenant_id=document.acl_scope.tenant_id,
                acl_allowed_roles=list(document.acl_scope.allowed_roles),
                acl_allowed_groups=list(document.acl_scope.allowed_groups),
                acl_is_public=document.acl_scope.is_public,
                valid_from=document.temporal.valid_from,
                valid_to=document.temporal.valid_to,
                ingested_at=document.temporal.ingested_at,
                source_version=document.temporal.source_version,
                source_tier=int(document.provenance.tier),
                source_uri=document.provenance.source_uri,
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
            doc_record.content_hash = document.content_hash
            doc_record.acl_tenant_id = document.acl_scope.tenant_id
            doc_record.acl_allowed_roles = list(document.acl_scope.allowed_roles)
            doc_record.acl_allowed_groups = list(document.acl_scope.allowed_groups)
            doc_record.acl_is_public = document.acl_scope.is_public
            doc_record.valid_from = document.temporal.valid_from
            doc_record.valid_to = document.temporal.valid_to
            doc_record.source_version = document.temporal.source_version
            doc_record.source_tier = int(document.provenance.tier)
            doc_record.source_uri = document.provenance.source_uri
            doc_record.provenance_confidence = document.provenance.confidence
            doc_record.provenance_verified = document.provenance.verified
            doc_record.metadata_json = document.metadata

            # Clear old chunks for clean replacement
            await session.execute(delete(ChunkRecord).where(ChunkRecord.doc_id == document.doc_id))

        # Insert new chunks
        for chunk in document.chunks:
            chunk_rec = cls._chunk_to_record(chunk)
            session.add(chunk_rec)

        # Stage DOCUMENT_INGESTED outbox event
        doc_payload: dict[str, Any] = {
            "doc_id": document.doc_id,
            "title": document.title,
            "version": document.version,
            "chunk_count": len(document.chunks),
            "tenant_id": document.acl_scope.tenant_id,
            "source_uri": document.provenance.source_uri,
        }
        OutboxService.stage_event(
            session=session,
            event_type=OutboxEventType.DOCUMENT_INGESTED,
            aggregate_type="document",
            aggregate_id=document.doc_id,
            payload=doc_payload,
        )

        # Stage CHUNK_UPSERTED outbox events for downstream Qdrant / Neo4j indexers
        for chunk in document.chunks:
            chunk_payload: dict[str, Any] = {
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "index": chunk.index,
                "text": chunk.text,
                "tokens": chunk.tokens,
                "acl_scope": {
                    "tenant_id": chunk.acl_scope.tenant_id,
                    "allowed_roles": list(chunk.acl_scope.allowed_roles),
                    "allowed_groups": list(chunk.acl_scope.allowed_groups),
                    "is_public": chunk.acl_scope.is_public,
                },
                "temporal": {
                    "valid_from": chunk.temporal.valid_from.isoformat(),
                    "valid_to": chunk.temporal.valid_to.isoformat()
                    if chunk.temporal.valid_to
                    else None,
                },
                "source_tier": int(chunk.provenance.tier),
                "entities": chunk.metadata.get("entities", []),
                "relations": chunk.metadata.get("relations", []),
            }
            OutboxService.stage_event(
                session=session,
                event_type=OutboxEventType.CHUNK_UPSERTED,
                aggregate_type="chunk",
                aggregate_id=chunk.chunk_id,
                payload=chunk_payload,
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
        OutboxService.stage_event(
            session=session,
            event_type=OutboxEventType.DOCUMENT_DELETED,
            aggregate_type="document",
            aggregate_id=doc_id,
            payload={"doc_id": doc_id},
        )

        # Stage CACHE_INVALIDATED outbox event
        OutboxService.stage_event(
            session=session,
            event_type=OutboxEventType.CACHE_INVALIDATED,
            aggregate_type="cache",
            aggregate_id=doc_id,
            payload={"doc_id": doc_id, "reason": "document_deletion"},
        )

        await session.delete(record)
        return True
