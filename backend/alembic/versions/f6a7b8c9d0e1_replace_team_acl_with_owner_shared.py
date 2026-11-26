"""replace tenant/role/group ACLs with owner/shared scopes

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-25 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Preserve denial for legacy restricted rows. A modern ACL with both fields
    # NULL is public, so formerly restricted rows without an owner get a sentinel
    # owner that no real identity can match. Public rows stay NULL/NULL.
    for table in ("documents", "chunks"):
        op.execute(
            f"UPDATE {table} SET owner_user_id = 'legacy-restricted' "
            "WHERE coalesce(acl_is_public, false) = false AND owner_user_id IS NULL"
        )
        op.drop_index(op.f(f"ix_{table}_acl_is_public"), table_name=table)
        op.drop_index(op.f(f"ix_{table}_acl_tenant_id"), table_name=table)
        op.add_column(
            table,
            sa.Column("shared_scope", sa.String(length=128), nullable=True),
        )
        op.create_index(
            op.f(f"ix_{table}_shared_scope"), table, ["shared_scope"], unique=False
        )
        op.drop_column(table, "acl_tenant_id")
        op.drop_column(table, "acl_allowed_roles")
        op.drop_column(table, "acl_allowed_groups")
        op.drop_column(table, "acl_is_public")

    op.add_column("threads", sa.Column("shared_scope", sa.String(length=128), nullable=True))
    op.create_index(op.f("ix_threads_shared_scope"), "threads", ["shared_scope"], unique=False)
    op.execute(
        "UPDATE threads SET shared_scope = COALESCE(NULLIF(acl_scope, ''), 'legacy-restricted') "
        "WHERE COALESCE(owner_user_id, '') = ''"
        " AND COALESCE(acl_scope, '') NOT IN ('', 'public')"
    )
    op.drop_column("threads", "acl_scope")
    op.drop_column("threads", "as_of_date")


def downgrade() -> None:
    for table in ("documents", "chunks"):
        op.add_column(
            table,
            sa.Column(
                "acl_tenant_id",
                sa.String(length=64),
                nullable=False,
                server_default="default",
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "acl_allowed_roles",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "acl_allowed_groups",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "acl_is_public",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        op.execute(
            f"UPDATE {table} SET acl_is_public = "
            "(owner_user_id IS NULL AND shared_scope IS NULL)"
        )
        op.execute(
            f"UPDATE {table} SET owner_user_id = NULL "
            "WHERE owner_user_id = 'legacy-restricted'"
        )
        op.create_index(
            op.f(f"ix_{table}_acl_is_public"), table, ["acl_is_public"], unique=False
        )
        op.create_index(
            op.f(f"ix_{table}_acl_tenant_id"), table, ["acl_tenant_id"], unique=False
        )
        op.drop_index(op.f(f"ix_{table}_shared_scope"), table_name=table)
        op.drop_column(table, "shared_scope")

    op.add_column(
        "threads",
        sa.Column("acl_scope", sa.String(length=64), nullable=False, server_default="public"),
    )
    op.add_column("threads", sa.Column("as_of_date", sa.String(length=32), nullable=True))
    op.execute(
        "UPDATE threads SET acl_scope = COALESCE("
        "NULLIF(shared_scope, ''), "
        "CASE WHEN owner_user_id IS NULL THEN 'public' ELSE 'legacy-restricted' END)"
    )
    op.drop_index(op.f("ix_threads_shared_scope"), table_name="threads")
    op.drop_column("threads", "shared_scope")
