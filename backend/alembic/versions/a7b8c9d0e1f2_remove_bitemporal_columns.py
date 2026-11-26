"""remove bi-temporal validity columns

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-25 00:00:00.000000

``threads.as_of_date`` was already removed by the owner/shared ACL revision.
These are the remaining validity-window columns created by the initial schema.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TEMPORAL_TABLES = (
    "documents",
    "chunks",
    "entities",
    "relations",
    "query_answers",
    "answers",
)
_TEMPORAL_COLUMNS = (
    "valid_from",
    "valid_to",
    "as_of",
    "as_of_date",
    "default_as_of_date",
)


def _existing_columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    # Only the initial documents/chunks tables carry these columns in the
    # canonical migration chain. The inspection keeps upgrades idempotent if a
    # deployment has drifted or Manual additions in the other listed tables.
    for table in _TEMPORAL_TABLES:
        existing = _existing_columns(table)
        for column in _TEMPORAL_COLUMNS:
            if column in existing:
                op.drop_column(table, column)


def downgrade() -> None:
    # Restore the canonical initial-schema columns. Legacy validity semantics
    # are not reconstructed: rows receive the migration time as valid_from and
    # an open-ended valid_to, while ingested_at remains the system timestamp.
    for table in ("documents", "chunks"):
        existing = _existing_columns(table)
        if "valid_from" not in existing:
            op.add_column(
                table,
                sa.Column(
                    "valid_from",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                ),
            )
            op.alter_column(
                table,
                "valid_from",
                existing_type=sa.DateTime(timezone=True),
                server_default=None,
            )
        if "valid_to" not in existing:
            op.add_column(
                table,
                sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
            )
