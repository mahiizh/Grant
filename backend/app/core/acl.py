from pydantic import BaseModel, ConfigDict, Field


class ACLScope(BaseModel):
    """Access Control List (ACL) scope attached to documents, chunks, and graph elements."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str = "default"
    allowed_roles: frozenset[str] = Field(default_factory=frozenset)
    allowed_groups: frozenset[str] = Field(default_factory=frozenset)
    is_public: bool = True

    @classmethod
    def public(cls, tenant_id: str = "default") -> "ACLScope":
        """Factory for unrestricted public scope within a tenant."""
        return cls(tenant_id=tenant_id, is_public=True)

    @classmethod
    def restricted(
        cls,
        allowed_roles: set[str] | frozenset[str],
        allowed_groups: set[str] | frozenset[str] | None = None,
        tenant_id: str = "default",
    ) -> "ACLScope":
        """Factory for restricted ACL scope requiring specific roles or groups."""
        return cls(
            tenant_id=tenant_id,
            allowed_roles=frozenset(allowed_roles),
            allowed_groups=frozenset(allowed_groups or set()),
            is_public=False,
        )

    def permits(
        self,
        user_roles: set[str] | frozenset[str],
        user_groups: set[str] | frozenset[str] | None = None,
        tenant_id: str = "default",
        is_admin: bool = False,
    ) -> bool:
        """Evaluate if a caller's credentials satisfy this ACL policy."""
        if self.tenant_id != tenant_id:
            return False

        if is_admin or self.is_public:
            return True

        caller_roles = frozenset(user_roles)
        if bool(self.allowed_roles & caller_roles):
            return True

        if user_groups:
            caller_groups = frozenset(user_groups)
            if bool(self.allowed_groups & caller_groups):
                return True

        return False

    def union(self, other: "ACLScope") -> "ACLScope":
        """Compute the union of two ACL scopes.

        An entity visible in either scope is visible in the union.
        """
        return ACLScope(
            tenant_id=self.tenant_id if self.tenant_id == other.tenant_id else "default",
            allowed_roles=self.allowed_roles | other.allowed_roles,
            allowed_groups=self.allowed_groups | other.allowed_groups,
            is_public=self.is_public or other.is_public,
        )
