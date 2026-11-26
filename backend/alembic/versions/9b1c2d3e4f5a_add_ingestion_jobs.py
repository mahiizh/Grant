"""add background ingestion jobs

Revision ID: 9b1c2d3e4f5a
Revises: a7b8c9d0e1f2
Create Date: 2026-11-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9b1c2d3e4f5a"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("job_id", sa.String(length=64), primary_key=True),
        sa.Column("document_id", sa.String(length=128), nullable=False),
        sa.Column("owner_user_id", sa.String(length=128), nullable=True),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("active_step", sa.String(length=64), server_default="queued", nullable=False),
        sa.Column("step_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("entity_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("relation_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("extraction_engine", sa.String(length=32), server_default="unknown", nullable=False),
        sa.Column("extraction_model", sa.String(length=256), server_default="", nullable=False),
        sa.Column("extraction_status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_ingestion_jobs_job_id"), "ingestion_jobs", ["job_id"], unique=False)
    op.create_index(op.f("ix_ingestion_jobs_document_id"), "ingestion_jobs", ["document_id"], unique=False)
    op.create_index(op.f("ix_ingestion_jobs_owner_user_id"), "ingestion_jobs", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_ingestion_jobs_status"), "ingestion_jobs", ["status"], unique=False)
    op.create_index(op.f("ix_ingestion_jobs_created_at"), "ingestion_jobs", ["created_at"], unique=False)
    op.create_index("ix_ingestion_jobs_owner_status", "ingestion_jobs", ["owner_user_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_owner_status", table_name="ingestion_jobs")
    op.drop_index(op.f("ix_ingestion_jobs_created_at"), table_name="ingestion_jobs")
    op.drop_index(op.f("ix_ingestion_jobs_status"), table_name="ingestion_jobs")
    op.drop_index(op.f("ix_ingestion_jobs_owner_user_id"), table_name="ingestion_jobs")
    op.drop_index(op.f("ix_ingestion_jobs_document_id"), table_name="ingestion_jobs")
    op.drop_index(op.f("ix_ingestion_jobs_job_id"), table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
