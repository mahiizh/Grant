"""step 4: link entity mentions to chunks

Revision ID: f7a8b9c0d1e2
Revises: 9b1c2d3e4f5a
Create Date: 2026-11-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "9b1c2d3e4f5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "entity_mentions",
        sa.Column("chunk_id", sa.String(length=128), nullable=True),
    )
    op.create_foreign_key(
        "fk_entity_mentions_chunk_id",
        "entity_mentions",
        "chunks",
        ["chunk_id"],
        ["chunk_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_entity_mentions_chunk_id"), "entity_mentions", ["chunk_id"], unique=False
    )
    op.create_index(
        "ix_entity_mentions_entity_chunk",
        "entity_mentions",
        ["entity_id", "chunk_id"],
        unique=False,
    )
    op.drop_constraint(
        "uq_entity_mentions_entity_source", "entity_mentions", type_="unique"
    )
    op.create_unique_constraint(
        "uq_entity_mentions_entity_source_chunk",
        "entity_mentions",
        ["entity_id", "source_id", "chunk_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_entity_mentions_entity_source_chunk", "entity_mentions", type_="unique"
    )
    op.create_unique_constraint(
        "uq_entity_mentions_entity_source",
        "entity_mentions",
        ["entity_id", "source_id"],
    )
    op.drop_index("ix_entity_mentions_entity_chunk", table_name="entity_mentions")
    op.drop_index(op.f("ix_entity_mentions_chunk_id"), table_name="entity_mentions")
    op.drop_constraint("fk_entity_mentions_chunk_id", "entity_mentions", type_="foreignkey")
    op.drop_column("entity_mentions", "chunk_id")
