from pydantic import BaseModel, ConfigDict


class ACLScope(BaseModel):
    """Resource access boundary: owner-private, shared, or public.

    ``owner_user_id`` and ``shared_scope`` are the only authorization dimensions.
    A scope with neither value is public. A scope with both values grants either
    the named owner or members of the named shared scope (used only when unioning
    equivalent entities during indexing).
    """

    model_config = ConfigDict(frozen=True)

    owner_user_id: str | None = None
    shared_scope: str | None = None

    @classmethod
    def public(cls) -> "ACLScope":
        """Factory for unrestricted data visible to every caller."""
        return cls()

    @classmethod
    def owner(cls, owner_user_id: str) -> "ACLScope":
        """Factory for data visible only to one user."""
        return cls(owner_user_id=owner_user_id)

    @classmethod
    def shared(cls, shared_scope: str) -> "ACLScope":
        """Factory for data visible to members of a named shared scope."""
        return cls(shared_scope=shared_scope)

    def permits(
        self,
        *,
        owner_user_id: str | None = None,
        shared_scope: str | None = None,
        shared_scopes: frozenset[str] | set[str] | None = None,
        is_admin: bool = False,
    ) -> bool:
        """Return whether a caller may access data carrying this scope."""
        if is_admin:
            return True

        if self.owner_user_id is not None and owner_user_id == self.owner_user_id:
            return True

        if self.shared_scope is not None:
            allowed = set(shared_scopes or ())
            if shared_scope is not None:
                allowed.add(shared_scope)
            if self.shared_scope in allowed:
                return True

        return self.owner_user_id is None and self.shared_scope is None

    def union(self, other: "ACLScope") -> "ACLScope":
        """Combine two scopes without widening access.

        Only one owner and one shared scope can be represented, so conflicting
        owners/scopes keep the first value and deny the second rather than
        falling back to public.
        """
        return ACLScope(
            owner_user_id=self.owner_user_id or other.owner_user_id,
            shared_scope=self.shared_scope or other.shared_scope,
        )
