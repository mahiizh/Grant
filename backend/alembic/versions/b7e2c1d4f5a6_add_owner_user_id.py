"""add owner_user_id to documents chunks threads messages

Revision ID: b7e2c1d4f5a6
Revises: a9cf8318b733
Create Date: 2026-11-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7e2c1d4f5a6"
down_revision: str | None = "a9cf8318b733"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("owner_user_id", sa.String(length=128), nullable=True))
    op.create_index(op.f("ix_documents_owner_user_id"), "documents", ["owner_user_id"], unique=False)

    op.add_column("chunks", sa.Column("owner_user_id", sa.String(length=128), nullable=True))
    op.create_index(op.f("ix_chunks_owner_user_id"), "chunks", ["owner_user_id"], unique=False)

    op.add_column("threads", sa.Column("owner_user_id", sa.String(length=128), nullable=True))
    op.create_index(op.f("ix_threads_owner_user_id"), "threads", ["owner_user_id"], unique=False)

    op.add_column("messages", sa.Column("owner_user_id", sa.String(length=128), nullable=True))
    op.create_index(op.f("ix_messages_owner_user_id"), "messages", ["owner_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_messages_owner_user_id"), table_name="messages")
    op.drop_column("messages", "owner_user_id")

    op.drop_index(op.f("ix_threads_owner_user_id"), table_name="threads")
    op.drop_column("threads", "owner_user_id")

    op.drop_index(op.f("ix_chunks_owner_user_id"), table_name="chunks")
    op.drop_column("chunks", "owner_user_id")

    op.drop_index(op.f("ix_documents_owner_user_id"), table_name="documents")
    op.drop_column("documents", "owner_user_id")
