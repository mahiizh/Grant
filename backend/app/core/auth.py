from typing import Any

from fastapi import Header, HTTPException, status

from app.core.acl import ACLScope
from app.core.config import get_settings
from app.retrieval.filters import RetrievalFilter


class AuthenticatedUser:
    """Dev-header authenticated identity with owner and shared-scope credentials."""

    def __init__(self, username: str, user_data: dict[str, Any]) -> None:
        self.username = username
        self.user_id: str = user_data["user_id"]
        self.name: str = user_data["name"]
        self.shared_scopes: set[str] = set(user_data.get("shared_scopes", []))
        self.is_admin: bool = bool(user_data.get("is_admin", False))

    def check_scope(self, scope: str) -> None:
        """Validate that the caller may request a named shared scope."""
        if self.is_admin or scope in self.shared_scopes:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"User '{self.username}' is not authorized for shared scope '{scope}'. "
                f"Allowed shared scopes: {sorted(self.shared_scopes)}"
            ),
        )

    def resolve_scope(self, requested_scope: str | None = None) -> str | None:
        """Validate and return an explicitly requested shared scope."""
        if requested_scope is None:
            return None
        self.check_scope(requested_scope)
        return requested_scope

    def to_acl_scope(self, requested_scope: str | None = None) -> ACLScope:
        """Build the ACL boundary for a query: shared when requested, owner otherwise."""
        scope = self.resolve_scope(requested_scope)
        if scope is not None:
            return ACLScope.shared(scope)
        if self.is_admin:
            return ACLScope.public()
        return ACLScope.owner(self.user_id)

    def to_retrieval_filter(self, requested_scope: str | None = None) -> RetrievalFilter:
        """Build the query-time ACL filter for this identity."""
        return RetrievalFilter(
            acl_scope=self.to_acl_scope(requested_scope),
            owner_user_id=self.user_id,
            is_admin=self.is_admin,
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
