"""step 5: persist answer source metadata

Revision ID: a1b2c3d4e5f6
Revises: f7a8b9c0d1e2
Create Date: 2026-11-26 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "answers",
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default="docs",
        ),
    )
    op.create_index(op.f("ix_answers_source"), "answers", ["source"], unique=False)
    op.add_column(
        "answers",
        sa.Column("path", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "answers",
        sa.Column(
            "top_score",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "answers",
        sa.Column("stage_timings_ms", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "messages",
        sa.Column("answer_metadata", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("messages", "answer_metadata")
    op.drop_column("answers", "stage_timings_ms")
    op.drop_column("answers", "top_score")
    op.drop_column("answers", "path")
    op.drop_index(op.f("ix_answers_source"), table_name="answers")
    op.drop_column("answers", "source")
