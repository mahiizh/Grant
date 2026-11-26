from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    LargeBinary,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class DocumentRecord(Base):
    """PostgreSQL table acting as the single source of truth for documents."""

    __tablename__ = "documents"

    doc_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # ACL Scope: owner-private or shared. NULL/NULL means public.
    shared_scope: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # Ingestion metadata
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    source_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Provenance
    source_tier: Mapped[int] = mapped_column(Integer, nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), default="document", nullable=False, index=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provenance_confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    provenance_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    chunks: Mapped[list["ChunkRecord"]] = relationship(
        "ChunkRecord", back_populates="document", cascade="all, delete-orphan"
    )


class ChunkRecord(Base):
    """PostgreSQL table holding chunk records linked to parent documents."""

    __tablename__ = "chunks"

    chunk_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    doc_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # ACL Scope: owner-private or shared. NULL/NULL means public.
    shared_scope: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # Provenance
    source_tier: Mapped[int] = mapped_column(Integer, nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), default="document", nullable=False, index=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provenance_confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    provenance_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    document: Mapped["DocumentRecord"] = relationship("DocumentRecord", back_populates="chunks")

    __table_args__ = (Index("ix_chunks_doc_id_index", "doc_id", "chunk_index"),)


class OutboxEventRecord(Base):
    """Transactional outbox table staging mutation events in the same DB transaction."""

    __tablename__ = "outbox_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_outbox_status_created", "status", "created_at"),)


class IngestionJobRecord(Base):
    """Queued upload plus the raw bytes the background worker must process.

    The HTTP handler only writes this row, so upload latency is independent of
    parsing, GLiNER extraction, entity resolution, and downstream indexing.
    """

    __tablename__ = "ingestion_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    active_step: Mapped[str] = mapped_column(
        String(64), default="queued", nullable=False
    )
    step_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    relation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extraction_engine: Mapped[str] = mapped_column(
        String(32), default="unknown", nullable=False
    )
    extraction_model: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    extraction_status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_ingestion_jobs_owner_status", "owner_user_id", "status"),)


class ThreadRecord(Base):
    """PostgreSQL table holding conversation threads."""

    __tablename__ = "threads"

    thread_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    shared_scope: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False, index=True
    )

    messages: Mapped[list["MessageRecord"]] = relationship(
        "MessageRecord",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="MessageRecord.created_at",
    )


class MessageRecord(Base):
    """PostgreSQL table holding individual glass-box turns within a conversation thread."""

    __tablename__ = "messages"

    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    thread_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("threads.thread_id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "user" | "assistant" | "system"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    raw_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    rewritten_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    route: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cache_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    pipeline_stages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    subgraph_nodes: Mapped[list[str]] = mapped_column(JSON, default=list)
    feedback: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "up" | "down"
    feedback_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    generations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    source_kind: Mapped[str] = mapped_column(String(16), default="docs", nullable=False)
    web_sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    query_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    answer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    thread: Mapped["ThreadRecord"] = relationship("ThreadRecord", back_populates="messages")


class QueryRecord(Base):
    """PostgreSQL source of truth for a user question in answer history."""

    __tablename__ = "queries"

    query_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    thread_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("threads.thread_id", ondelete="CASCADE"), nullable=True, index=True
    )
    owner_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    raw_query: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    answer_policy: Mapped[str] = mapped_column(String(32), default="grounded_plus_web", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    answers: Mapped[list["AnswerRecord"]] = relationship(
        "AnswerRecord", back_populates="query", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_queries_owner_hash", "owner_user_id", "query_hash"),
    )


class AnswerRecord(Base):
    """PostgreSQL source of truth for an answer and its source label in history."""

    __tablename__ = "answers"

    answer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    query_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("queries.query_id", ondelete="CASCADE"), nullable=False, index=True
    )
    thread_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("threads.thread_id", ondelete="CASCADE"), nullable=True, index=True
    )
    owner_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(16), default="docs", nullable=False, index=True)
    is_abstention: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    web_sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    query: Mapped["QueryRecord"] = relationship("QueryRecord", back_populates="answers")


class EntityRecord(Base):
    """Canonical entity registry. Qdrant holds only vector+entity_id+type_group+owner_user_id."""

    __tablename__ = "entities"

    entity_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    type_group: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        Index("ix_entities_owner_type_group", "owner_user_id", "type_group"),
    )


class EntityMentionRecord(Base):
    """PostgreSQL table linking canonical entities to documents/sources."""

    __tablename__ = "entity_mentions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="document")
    doc_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=True, index=True
    )
    chunk_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("chunks.chunk_id", ondelete="CASCADE"), nullable=True, index=True
    )
    owner_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    surface_form: Mapped[str] = mapped_column(Text, nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, default="Concept")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "source_id",
            "chunk_id",
            name="uq_entity_mentions_entity_source_chunk",
        ),
        CheckConstraint(
            "source_kind <> 'document' OR doc_id IS NOT NULL",
            name="ck_entity_mentions_doc_source_has_doc_id",
        ),
        Index("ix_entity_mentions_owner_entity", "owner_user_id", "entity_id"),
        Index("ix_entity_mentions_source_kind", "source_kind", "source_id"),
        Index("ix_entity_mentions_entity_chunk", "entity_id", "chunk_id"),
    )


class SpanRecord(Base):
    """PostgreSQL table holding OpenTelemetry trace spans."""

    __tablename__ = "spans"

    span_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    parent_span_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    status_code: Mapped[str] = mapped_column(String(32), default="OK", nullable=False)
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    __table_args__ = (Index("ix_spans_trace_start", "trace_id", "start_time"),)
