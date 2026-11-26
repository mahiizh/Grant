from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from qdrant_client import models

from app.core.acl import ACLScope
from app.domain import Chunk


class RetrievalFilter(BaseModel):
    """Shared ACL filter applied across dense, sparse, graph, and cache paths."""

    model_config = ConfigDict(frozen=True)

    acl_scope: ACLScope = Field(default_factory=ACLScope.public)
    doc_ids: frozenset[str] | None = None
    owner_user_id: str | None = None
    is_admin: bool = False

    @staticmethod
    def _payload_acl_scope(payload: dict[str, Any]) -> ACLScope | None:
        """Parse a store payload, default-denying unusable ACL metadata."""
        acl = payload.get("acl_scope")

        if isinstance(acl, dict):
            owner = acl.get("owner_user_id")
            shared = acl.get("shared_scope")
            # Legacy restricted payloads (roles/groups/tenant) have no modern
            # equivalent and are denied before any public fallback is considered.
            legacy_restricted = any(
                acl.get(key) for key in ("tenant_id", "allowed_roles", "allowed_groups")
            )
            if legacy_restricted:
                return None
            if owner is not None or shared is not None:
                return ACLScope(owner_user_id=owner or None, shared_scope=shared or None)
            # ``ACLScope.public().model_dump()`` contains both keys with null
            # values. Older public payloads only carry an explicit public flag.
            if "owner_user_id" in acl or "shared_scope" in acl or acl.get("is_public") is True:
                return ACLScope.public()
            return None

        if payload.get("acl_is_public") is True:
            return ACLScope.public()
        return None

    def permits_chunk(self, chunk: Chunk) -> bool:
        """Evaluate document scoping, ownership, and ACL permission for a chunk."""
        if self.doc_ids is not None and chunk.doc_id not in self.doc_ids:
            return False

        if (
            not self.is_admin
            and chunk.owner_user_id is not None
            and chunk.owner_user_id != self.owner_user_id
        ):
            return False

        return chunk.acl_scope.permits(
            owner_user_id=self.owner_user_id,
            shared_scope=self.acl_scope.shared_scope,
            is_admin=self.is_admin,
        )

    def permits_payload(self, payload: dict[str, Any]) -> bool:
        """Defense-in-depth ACL check for serialized Qdrant payloads."""
        if self.doc_ids is not None and payload.get("doc_id") not in self.doc_ids:
            return False

        scope = self._payload_acl_scope(payload)
        if scope is None:
            return False

        payload_owner = payload.get("owner_user_id") or scope.owner_user_id
        if (
            not self.is_admin
            and payload_owner is not None
            and payload_owner != self.owner_user_id
        ):
            return False

        return scope.permits(
            owner_user_id=self.owner_user_id,
            shared_scope=self.acl_scope.shared_scope,
            is_admin=self.is_admin,
        )

    def to_qdrant_filter(self) -> models.Filter:
        """Build an in-query Qdrant filter for the exact ACL boundary."""
        must: list[models.Condition] = []
        if self.doc_ids is not None:
            must.append(
                models.FieldCondition(
                    key="doc_id",
                    match=models.MatchAny(any=sorted(self.doc_ids)),
                )
            )

        if self.is_admin:
            return models.Filter(must=must) if must else models.Filter()

        acl_should: list[models.Condition] = []
        if self.owner_user_id:
            acl_should.extend(
                [
                    models.FieldCondition(
                        key="owner_user_id",
                        match=models.MatchValue(value=self.owner_user_id),
                    ),
                    models.FieldCondition(
                        key="acl_scope.owner_user_id",
                        match=models.MatchValue(value=self.owner_user_id),
                    ),
                ]
            )

        if self.acl_scope.shared_scope is not None:
            acl_should.append(
                models.FieldCondition(
                    key="acl_scope.shared_scope",
                    match=models.MatchValue(value=self.acl_scope.shared_scope),
                )
            )

        # Usable public payloads: no owner and no shared scope. Both null and
        # empty-string legacy payloads are accepted; Python re-checks each hit.
        public_fields = (
            "owner_user_id",
            "acl_scope.owner_user_id",
            "acl_scope.shared_scope",
        )
        acl_should.append(
            models.Filter(
                must=[models.IsNullCondition(is_null=models.PayloadField(key=key)) for key in public_fields]
            )
        )
        acl_should.append(
            models.Filter(
                must=[
                    models.IsEmptyCondition(is_empty=models.PayloadField(key=key))
                    for key in public_fields
                ]
            )
        )
        # Legacy public markers from the pre-owner/shared index schema.
        acl_should.append(
            models.FieldCondition(
                key="acl_scope.is_public",
                match=models.MatchValue(value=True),
            )
        )
        acl_should.append(
            models.FieldCondition(
                key="acl_is_public",
                match=models.MatchValue(value=True),
            )
        )

        must.append(models.Filter(should=acl_should))
        return models.Filter(must=must)

    def to_cypher_predicate(self, node_alias: str = "n") -> tuple[str, dict[str, Any]]:
        """Build a parameterized Cypher ACL predicate for a node or relationship."""
        params: dict[str, Any] = {
            "acl_owner_user_id": self.owner_user_id or "",
            "acl_shared_scope": self.acl_scope.shared_scope,
            "acl_is_admin": self.is_admin,
        }
        alias = node_alias
        owner_clause = (
            f"($acl_owner_user_id <> ''"
            f" AND coalesce({alias}.owner_user_id, '') = $acl_owner_user_id)"
        )
        shared_clause = (
            "($acl_shared_scope IS NOT NULL"
            f" AND coalesce({alias}.shared_scope, '') = $acl_shared_scope)"
        )
        # Default-deny legacy restricted nodes that still carry pre-cleanup ACL
        # properties but no modern owner/shared values.
        public_clause = (
            f"(coalesce({alias}.owner_user_id, '') = ''"
            f" AND coalesce({alias}.shared_scope, '') = ''"
            f" AND coalesce({alias}.is_public, true) = true"
            f" AND size(coalesce({alias}.owner_user_ids, [])) = 0"
            f" AND coalesce({alias}.acl_owner_user_id, '') = ''"
            f" AND coalesce({alias}.acl_shared_scope, '') = ''"
            f" AND coalesce({alias}.acl_is_public, true) = true)"
        )
        clause = f"($acl_is_admin OR {owner_clause} OR {shared_clause} OR {public_clause})"
        return clause, params
