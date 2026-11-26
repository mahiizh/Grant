import hashlib
import re

from app.core.acl import ACLScope

LEGACY_PROMPT_VERSION = "v1"
GROUNDED_ONLY_PROMPT_VERSION = f"{LEGACY_PROMPT_VERSION}:grounded_only"


def prompt_version_lookup_chain(prompt_version: str) -> tuple[str, ...]:
    """Return policy-scoped keys plus the legacy grounded-only key when compatible.

    Entries written before answer policies existed used ``v1`` and were always
    grounded-only. They can safely be read only by the grounded-only policy;
    policy-specific keys are still preferred and remain write-isolated.
    """
    if prompt_version == GROUNDED_ONLY_PROMPT_VERSION:
        return (prompt_version, LEGACY_PROMPT_VERSION)
    return (prompt_version,)


def normalize_query(query: str) -> str:
    """Normalize query text by lowercasing, stripping whitespace, and normalizing spaces."""
    cleaned = re.sub(r"\s+", " ", query.strip().lower())
    return cleaned


def hash_acl_scope(acl_scope: ACLScope) -> str:
    """Compute a deterministic hash of the owner/shared security boundary."""
    raw = f"{acl_scope.owner_user_id or ''}|{acl_scope.shared_scope or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def generate_exact_cache_key(
    query: str,
    acl_scope: ACLScope,
    index_version: int = 1,
    prompt_version: str = "v1",
    owner_user_id: str | None = None,
) -> str:
    """Generate isolated cache key bound to query, ACL, owner, index, and prompt."""
    norm_q = normalize_query(query)
    acl_hash = hash_acl_scope(acl_scope)
    owner_hash = hashlib.sha256((owner_user_id or "anon").encode("utf-8")).hexdigest()[:12]
    q_hash = hashlib.sha256(norm_q.encode("utf-8")).hexdigest()[:16]
    prefix = f"cache:exact:v{index_version}:{prompt_version}"
    return f"{prefix}:{owner_hash}:{acl_hash}:{q_hash}"
