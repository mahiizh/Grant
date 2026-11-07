from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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

    def permits_chunk(self, chunk: Chunk) -> bool:
        """Evaluate both ACL permissions and bi-temporal validity for a chunk."""
        # 1. Document ID filtering (if scoped to specific documents)
        if self.doc_ids is not None and chunk.doc_id not in self.doc_ids:
            return False

        # 2. ACL Permission check
        if not chunk.acl_scope.permits(
            user_roles=self.user_roles,
            user_groups=self.user_groups,
            tenant_id=self.acl_scope.tenant_id,
            is_admin=self.is_admin,
        ):
            return False

        # 3. Bi-temporal "as of" validity check
        return not (self.as_of_time is not None and not chunk.temporal.is_valid_at(self.as_of_time))

    def permits_payload(self, payload: dict[str, Any]) -> bool:
        """Evaluate against serialized chunk payload in vector stores."""
        # Check tenant and doc_ids
        acl = payload.get("acl_scope", {})
        tenant_id = acl.get("tenant_id", "default")
        if tenant_id != self.acl_scope.tenant_id:
            return False

        if self.doc_ids is not None and payload.get("doc_id") not in self.doc_ids:
            return False

        is_public = acl.get("is_public", True)
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

    def to_cypher_clause(self, node_alias: str = "n") -> str:
        """Generate Cypher WHERE predicate for in-query graph filtering."""
        clauses: list[str] = []
        if not self.is_admin:
            clauses.append(
                f"({node_alias}.is_public = true OR "
                f"{node_alias}.tenant_id = '{self.acl_scope.tenant_id}')"
            )

        if self.as_of_time is not None:
            as_of_iso = self.as_of_time.astimezone(UTC).isoformat()
            clauses.append(f"{node_alias}.valid_from <= datetime('{as_of_iso}')")
            clauses.append(
                f"({node_alias}.valid_to IS NULL OR "
                f"{node_alias}.valid_to > datetime('{as_of_iso}'))"
            )

        return " AND ".join(clauses) if clauses else "true"
