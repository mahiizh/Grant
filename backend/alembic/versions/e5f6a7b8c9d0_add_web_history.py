"""add web source metadata and query/answer history

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-25 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("source_kind", sa.String(length=32), server_default="document", nullable=False))
    op.create_index(op.f("ix_documents_source_kind"), "documents", ["source_kind"], unique=False)
    op.add_column("documents", sa.Column("url", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("chunks", sa.Column("source_kind", sa.String(length=32), server_default="document", nullable=False))
    op.create_index(op.f("ix_chunks_source_kind"), "chunks", ["source_kind"], unique=False)
    op.add_column("chunks", sa.Column("url", sa.Text(), nullable=True))
    op.add_column("chunks", sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("messages", sa.Column("source_kind", sa.String(length=16), server_default="docs", nullable=False))
    op.add_column("messages", sa.Column("web_sources", sa.JSON(), server_default=sa.text("'[]'"), nullable=False))
    op.add_column("messages", sa.Column("query_id", sa.String(length=64), nullable=True))
    op.add_column("messages", sa.Column("answer_id", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_messages_query_id"), "messages", ["query_id"], unique=False)
    op.create_index(op.f("ix_messages_answer_id"), "messages", ["answer_id"], unique=False)

    op.create_table(
        "queries",
        sa.Column("query_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "thread_id",
            sa.String(length=64),
            sa.ForeignKey("threads.thread_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("owner_user_id", sa.String(length=128), nullable=True),
        sa.Column("raw_query", sa.Text(), nullable=False),
        sa.Column("rewritten_query", sa.Text(), nullable=True),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "answer_policy",
            sa.String(length=32),
            server_default="grounded_plus_web",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_queries_thread_id"), "queries", ["thread_id"], unique=False)
    op.create_index(op.f("ix_queries_owner_user_id"), "queries", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_queries_query_hash"), "queries", ["query_hash"], unique=False)
    op.create_index("ix_queries_owner_hash", "queries", ["owner_user_id", "query_hash"], unique=False)

    op.create_table(
        "answers",
        sa.Column("answer_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "query_id",
            sa.String(length=64),
            sa.ForeignKey("queries.query_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "thread_id",
            sa.String(length=64),
            sa.ForeignKey("threads.thread_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("owner_user_id", sa.String(length=128), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.String(length=16), server_default="docs", nullable=False),
        sa.Column("is_abstention", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("citations", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("web_sources", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_answers_query_id"), "answers", ["query_id"], unique=False)
    op.create_index(op.f("ix_answers_thread_id"), "answers", ["thread_id"], unique=False)
    op.create_index(op.f("ix_answers_owner_user_id"), "answers", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_answers_source_kind"), "answers", ["source_kind"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_messages_answer_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_query_id"), table_name="messages")
    op.drop_column("messages", "answer_id")
    op.drop_column("messages", "query_id")
    op.drop_table("answers")
    op.drop_table("queries")
    op.drop_column("messages", "web_sources")
    op.drop_column("messages", "source_kind")
    op.drop_column("chunks", "fetched_at")
    op.drop_column("chunks", "url")
    op.drop_index(op.f("ix_chunks_source_kind"), table_name="chunks")
    op.drop_column("chunks", "source_kind")
    op.drop_column("documents", "fetched_at")
    op.drop_column("documents", "url")
    op.drop_index(op.f("ix_documents_source_kind"), table_name="documents")
    op.drop_column("documents", "source_kind")
