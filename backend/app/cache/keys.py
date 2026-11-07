import hashlib
import re

from app.core.acl import ACLScope


def normalize_query(query: str) -> str:
    """Normalize query text by lowercasing, stripping whitespace, and normalizing spaces."""
    cleaned = re.sub(r"\s+", " ", query.strip().lower())
    return cleaned


def hash_acl_scope(acl_scope: ACLScope) -> str:
    """Compute a deterministic hash representing caller's exact security boundary."""
    roles_str = ",".join(sorted(acl_scope.allowed_roles))
    groups_str = ",".join(sorted(acl_scope.allowed_groups))
    raw = f"{acl_scope.tenant_id}|{roles_str}|{groups_str}|{acl_scope.is_public}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def generate_exact_cache_key(
    query: str,
    acl_scope: ACLScope,
    index_version: int = 1,
    prompt_version: str = "v1",
) -> str:
    """Generate isolated cache key bound to query, permissions, index version, and prompt."""
    norm_q = normalize_query(query)
    acl_hash = hash_acl_scope(acl_scope)
    q_hash = hashlib.sha256(norm_q.encode("utf-8")).hexdigest()[:16]
    prefix = f"cache:exact:{acl_scope.tenant_id}:v{index_version}:{prompt_version}"
    return f"{prefix}:{acl_hash}:{q_hash}"
