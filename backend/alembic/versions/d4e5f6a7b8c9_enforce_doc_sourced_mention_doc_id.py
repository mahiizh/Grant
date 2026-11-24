"""enforce doc-sourced mention doc_id

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-24 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Backfill doc-sourced mentions that lost doc_id due to pre-save FK workaround.
    op.execute(
        """
        UPDATE entity_mentions
        SET doc_id = source_id
        WHERE source_kind = 'document' AND doc_id IS NULL
        """
    )
    # Remove any remaining invalid doc-sourced mentions that cannot be linked.
    op.execute(
        """
        DELETE FROM entity_mentions
        WHERE source_kind = 'document' AND doc_id IS NULL
        """
    )
    op.create_check_constraint(
        "ck_entity_mentions_doc_source_has_doc_id",
        "entity_mentions",
        "source_kind <> 'document' OR doc_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_entity_mentions_doc_source_has_doc_id", "entity_mentions", type_="check")
