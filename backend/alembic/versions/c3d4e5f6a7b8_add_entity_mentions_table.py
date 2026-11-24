"""add entity mentions and entities tables

Revision ID: c3d4e5f6a7b8
Revises: b7e2c1d4f5a6
Create Date: 2026-11-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b7e2c1d4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("type_group", sa.String(64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=128), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("entity_id"),
    )
    op.create_index(op.f("ix_entities_owner_user_id"), "entities", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_entities_type_group"), "entities", ["type_group"], unique=False)
    op.create_index("ix_entities_owner_type_group", "entities", ["owner_user_id", "type_group"], unique=False)

    op.create_table(
        "entity_mentions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("doc_id", sa.String(length=128), nullable=True),
        sa.Column("owner_user_id", sa.String(length=128), nullable=True),
        sa.Column("surface_form", sa.Text(), nullable=False),
        sa.Column("mention_count", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["doc_id"], ["documents.doc_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_id", "source_id", name="uq_entity_mentions_entity_source"),
    )
    op.create_index(op.f("ix_entity_mentions_doc_id"), "entity_mentions", ["doc_id"], unique=False)
    op.create_index(op.f("ix_entity_mentions_entity_id"), "entity_mentions", ["entity_id"], unique=False)
    op.create_index(op.f("ix_entity_mentions_owner_entity"), "entity_mentions", ["owner_user_id", "entity_id"], unique=False)
    op.create_index(op.f("ix_entity_mentions_owner_user_id"), "entity_mentions", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_entity_mentions_source_id"), "entity_mentions", ["source_id"], unique=False)
    op.create_index(op.f("ix_entity_mentions_source_kind"), "entity_mentions", ["source_kind", "source_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_entity_mentions_source_kind"), table_name="entity_mentions")
    op.drop_index(op.f("ix_entity_mentions_source_id"), table_name="entity_mentions")
    op.drop_index(op.f("ix_entity_mentions_owner_user_id"), table_name="entity_mentions")
    op.drop_index(op.f("ix_entity_mentions_owner_entity"), table_name="entity_mentions")
    op.drop_index(op.f("ix_entity_mentions_entity_id"), table_name="entity_mentions")
    op.drop_index(op.f("ix_entity_mentions_doc_id"), table_name="entity_mentions")
    op.drop_table("entity_mentions")
    op.drop_index("ix_entities_owner_type_group", table_name="entities")
    op.drop_index(op.f("ix_entities_type_group"), table_name="entities")
    op.drop_index(op.f("ix_entities_owner_user_id"), table_name="entities")
    op.drop_table("entities")
