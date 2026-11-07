from typing import Any

from fastapi import Header, HTTPException, status

from app.core.acl import ACLScope
from app.core.config import get_settings


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

    def to_acl_scope(self, requested_scope: str | None = None) -> ACLScope:
        """Resolve ACLScope domain model enforced against identity credentials."""
        scope = requested_scope or (
            "data-platform" if "data-platform" in self.allowed_scopes else list(self.allowed_scopes)[0]
        )
        self.check_scope(scope)
        if scope == "public":
            return ACLScope.public()
        return ACLScope.restricted(
            allowed_roles=self.roles | {scope},
            allowed_groups=self.groups | {scope},
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
