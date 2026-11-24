from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from qdrant_client import models

from app.core.acl import ACLScope
from app.domain import Chunk


class RetrievalFilter(BaseModel):
    """Shared filter criteria applied at query-time across vector, sparse, and graph retrievers."""

    model_config = ConfigDict(frozen=True)

    acl_scope: ACLScope = Field(default_factory=ACLScope.public)
    user_roles: frozenset[str] = Field(default_factory=frozenset)
    user_groups: frozenset[str] = Field(default_factory=frozenset)
    is_admin: bool = False
    as_of_time: datetime | None = None
    doc_ids: frozenset[str] | None = None
    owner_user_id: str | None = None

    def permits_chunk(self, chunk: Chunk) -> bool:
        """Evaluate ownership, ACL permissions, and bi-temporal validity for a chunk."""
        # 1. Document ID filtering (if scoped to specific documents)
        if self.doc_ids is not None and chunk.doc_id not in self.doc_ids:
            return False

        # 2. Ownership isolation: enforce for owner-tagged data; legacy/unowned
        # data falls back to ACL (eval corpus/tests and pre-migration rows).
        if self.owner_user_id is not None:
            chunk_owner = getattr(chunk, "owner_user_id", None)
            if chunk_owner is not None and chunk_owner != self.owner_user_id:
                return False

        # 3. ACL Permission check
        if not chunk.acl_scope.permits(
            user_roles=self.user_roles,
            user_groups=self.user_groups,
            tenant_id=self.acl_scope.tenant_id,
            is_admin=self.is_admin,
        ):
            return False

        # 4. Bi-temporal "as of" validity check
        return not (self.as_of_time is not None and not chunk.temporal.is_valid_at(self.as_of_time))

    def permits_payload(self, payload: dict[str, Any]) -> bool:
        """Evaluate against serialized chunk payload in vector stores.

        Default-deny: a payload without a usable ``acl_scope`` is never treated as
        public. This is defense-in-depth behind the Qdrant query filter.
        """
        acl = payload.get("acl_scope")
        if not isinstance(acl, dict):
            return False

        if acl.get("tenant_id") != self.acl_scope.tenant_id:
            return False

        if self.owner_user_id is not None:
            payload_owner = payload.get("owner_user_id")
            if payload_owner is not None and payload_owner != self.owner_user_id:
                return False

        if self.doc_ids is not None and payload.get("doc_id") not in self.doc_ids:
            return False

        is_public = acl.get("is_public", False)
        if not self.is_admin and not is_public:
            allowed_roles = set(acl.get("allowed_roles", []))
            allowed_groups = set(acl.get("allowed_groups", []))
            if not bool(allowed_roles & self.user_roles) and not bool(
                allowed_groups & self.user_groups
            ):
                return False

        # Check temporal validity
        if self.as_of_time is not None:
            temporal = payload.get("temporal", {})
            valid_from_str = temporal.get("valid_from")
            valid_to_str = temporal.get("valid_to")
            if valid_from_str:
                valid_from = datetime.fromisoformat(valid_from_str)
                if self.as_of_time < valid_from:
                    return False
            if valid_to_str:
                valid_to = datetime.fromisoformat(valid_to_str)
                if self.as_of_time >= valid_to:
                    return False

        return True

    def to_qdrant_filter(self) -> models.Filter:
        """Build a Qdrant payload filter so ACL/temporal pruning happens in-query.

        The returned filter is applied *before* ANN search, so the retriever no
        longer relies on over-fetching candidates and filtering them in Python.
        """
        must: list[models.Condition] = [
            models.FieldCondition(
                key="acl_scope.tenant_id",
                match=models.MatchValue(value=self.acl_scope.tenant_id),
            )
        ]
        if self.owner_user_id is not None:
            must.append(
                models.Filter(
                    should=[
                        models.FieldCondition(
                            key="owner_user_id",
                            match=models.MatchValue(value=self.owner_user_id),
                        ),
                        models.IsNullCondition(is_null=models.PayloadField(key="owner_user_id")),
                        models.IsEmptyCondition(is_empty=models.PayloadField(key="owner_user_id")),
                    ]
                )
            )

        if not self.is_admin:
            should: list[models.Condition] = [
                models.FieldCondition(
                    key="acl_scope.is_public",
                    match=models.MatchValue(value=True),
                )
            ]
            if self.user_roles:
                should.append(
                    models.FieldCondition(
                        key="acl_scope.allowed_roles",
                        match=models.MatchAny(any=sorted(self.user_roles)),
                    )
                )
            if self.user_groups:
                should.append(
                    models.FieldCondition(
                        key="acl_scope.allowed_groups",
                        match=models.MatchAny(any=sorted(self.user_groups)),
                    )
                )
            must.append(models.Filter(should=should))

        if self.doc_ids is not None:
            must.append(
                models.FieldCondition(
                    key="doc_id",
                    match=models.MatchAny(any=sorted(self.doc_ids)),
                )
            )

        if self.as_of_time is not None:
            as_of = self.as_of_time.astimezone(UTC)
            must.append(
                models.FieldCondition(
                    key="temporal.valid_from",
                    range=models.DatetimeRange(lte=as_of),
                )
            )
            must.append(
                models.Filter(
                    should=[
                        models.IsEmptyCondition(
                            is_empty=models.PayloadField(key="temporal.valid_to")
                        ),
                        models.FieldCondition(
                            key="temporal.valid_to",
                            range=models.DatetimeRange(gt=as_of),
                        ),
                    ]
                )
            )

        return models.Filter(must=must)

    def to_cypher_predicate(self, node_alias: str = "n") -> tuple[str, dict[str, Any]]:
        """Build a parameterized Cypher ACL/temporal/owner predicate for a node or relationship.

        Returns the predicate plus the parameters it binds. Never interpolates
        caller-controlled values into the query string.
        """
        params: dict[str, Any] = {
            "acl_tenant_id": self.acl_scope.tenant_id,
            "acl_is_admin": self.is_admin,
            "acl_user_roles": sorted(self.user_roles),
            "acl_user_groups": sorted(self.user_groups),
            "acl_as_of": self.as_of_time.astimezone(UTC).isoformat()
            if self.as_of_time is not None
            else None,
            "owner_user_id": self.owner_user_id,
        }
        alias = node_alias
        clause = (
            f"(coalesce({alias}.acl_tenant_id, 'default') = $acl_tenant_id"
            f" AND ($owner_user_id IS NULL OR "
            f"(coalesce({alias}.owner_user_id, '') = '' AND size(coalesce({alias}.owner_user_ids, [])) = 0) OR "
            f"coalesce({alias}.owner_user_id, '') = $owner_user_id OR "
            f"$owner_user_id IN coalesce({alias}.owner_user_ids, []))"
            f" AND ($acl_is_admin OR coalesce({alias}.acl_is_public, false)"
            f" OR any(role IN coalesce({alias}.acl_allowed_roles, [])"
            f" WHERE role IN $acl_user_roles)"
            f" OR any(grp IN coalesce({alias}.acl_allowed_groups, [])"
            f" WHERE grp IN $acl_user_groups)))"
            f" AND ($acl_as_of IS NULL OR ("
            f"datetime(coalesce({alias}.valid_from, '1970-01-01T00:00:00Z'))"
            f" <= datetime($acl_as_of)"
            f" AND ({alias}.valid_to IS NULL"
            f" OR datetime({alias}.valid_to) > datetime($acl_as_of))))"
        )
        return clause, params
