from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
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

    # ACL Scope
    acl_tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    acl_allowed_roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    acl_allowed_groups: Mapped[list[str]] = mapped_column(JSON, default=list)
    acl_is_public: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Temporal Bounds
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    source_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Provenance
    source_tier: Mapped[int] = mapped_column(Integer, nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
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

    # ACL Scope
    acl_tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    acl_allowed_roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    acl_allowed_groups: Mapped[list[str]] = mapped_column(JSON, default=list)
    acl_is_public: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Temporal Bounds
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Provenance
    source_tier: Mapped[int] = mapped_column(Integer, nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
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


class ThreadRecord(Base):
    """PostgreSQL table holding conversation threads."""

    __tablename__ = "threads"

    thread_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    acl_scope: Mapped[str] = mapped_column(String(64), default="data-platform", nullable=False)
    as_of_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    thread: Mapped["ThreadRecord"] = relationship("ThreadRecord", back_populates="messages")


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
