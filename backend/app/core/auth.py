from datetime import datetime
from typing import Any

from fastapi import Header, HTTPException, status

from app.core.acl import ACLScope
from app.core.config import get_settings
from app.retrieval.filters import RetrievalFilter

# Deterministic primary scope when a request does not name one. Ordering is
# explicit so behaviour never depends on set iteration order.
DEFAULT_SCOPE_PRIORITY: tuple[str, ...] = (
    "data-platform",
    "sre",
    "payments",
    "core-banking",
    "executive-audit",
)


class AuthenticatedUser:
    def __init__(self, username: str, user_data: dict[str, Any]) -> None:
        self.username = username
        self.user_id: str = user_data["user_id"]
        self.name: str = user_data["name"]
        self.allowed_scopes: set[str] = set(user_data.get("allowed_scopes", ["public"]))
        self.roles: set[str] = set(user_data.get("roles", []))
        self.groups: set[str] = set(user_data.get("groups", []))

    def check_scope(self, scope: str) -> None:
        """Validate if the user is authorized to access the requested ACL scope."""
        if scope != "public" and scope not in self.allowed_scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"User '{self.username}' is not authorized for scope '{scope}'. "
                    f"Allowed scopes: {sorted(self.allowed_scopes)}"
                ),
            )

    def resolve_scope(self, requested_scope: str | None = None) -> str:
        """Resolve the requested scope, or a deterministic primary scope if omitted."""
        if requested_scope:
            self.check_scope(requested_scope)
            return requested_scope

        for candidate in DEFAULT_SCOPE_PRIORITY:
            if candidate in self.allowed_scopes:
                return candidate

        non_public = sorted(scope for scope in self.allowed_scopes if scope != "public")
        return non_public[0] if non_public else "public"

    def to_acl_scope(self, requested_scope: str | None = None) -> ACLScope:
        """Resolve ACLScope domain model enforced against identity credentials."""
        scope = self.resolve_scope(requested_scope)
        if scope == "public":
            return ACLScope.public()
        return ACLScope.restricted(
            allowed_roles=self.roles | {scope},
            allowed_groups=self.groups | {scope},
        )

    def to_retrieval_filter(
        self,
        requested_scope: str | None = None,
        as_of_time: datetime | None = None,
    ) -> RetrievalFilter:
        """Build the query-time ACL/temporal/owner filter for this identity."""
        acl_scope = self.to_acl_scope(requested_scope)
        return RetrievalFilter(
            acl_scope=acl_scope,
            user_roles=acl_scope.allowed_roles,
            user_groups=acl_scope.allowed_groups,
            as_of_time=as_of_time,
            owner_user_id=self.user_id,
        )


async def get_current_user(
    x_dev_user: str | None = Header(None, alias="X-Dev-User"),
) -> AuthenticatedUser:
    """FastAPI dependency resolving authenticated identity from X-Dev-User header."""
    settings = get_settings()
    username = (x_dev_user or "alice").strip().lower()
    user_data = settings.DEV_USERS.get(username)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unknown dev user '{x_dev_user}'. Known users: {list(settings.DEV_USERS.keys())}",
        )
    return AuthenticatedUser(username, user_data)
