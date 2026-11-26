import hashlib
import re

from app.core.acl import ACLScope

DEFAULT_INDEX_VERSION = 0
LEGACY_PROMPT_VERSION = "v1"


def normalize_query(query: str) -> str:
    """Normalize query text by lowercasing, stripping whitespace, and normalizing spaces."""
    return re.sub(r"\s+", " ", query.strip().lower())


def hash_acl_scope(acl_scope: ACLScope) -> str:
    """Deterministic hash of an ACL boundary, retained for diagnostics only."""
    raw = f"{acl_scope.owner_user_id or ''}|{acl_scope.shared_scope or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def generate_exact_cache_key(
    query: str,
    acl_scope: ACLScope | None = None,
    index_version: int = DEFAULT_INDEX_VERSION,
    prompt_version: str = LEGACY_PROMPT_VERSION,
    owner_user_id: str | None = None,
    answer_policy: str | None = None,
) -> str:
    """Return the exact SHA-256 key for one owner-scoped answer.

    The cache is exact, not semantic: the only inputs are the owner, the
    per-owner index version, the prompt revision, the answer policy, and the
    normalized question text. ``acl_scope`` is accepted for call-site
    compatibility but deliberately excluded so the key matches the documented
    contract exactly.
    """
    policy = answer_policy
    if policy is None and ":" in prompt_version:
        policy = prompt_version.rsplit(":", 1)[-1]
    policy = policy or "grounded_only"
    raw = "|".join(
        (
            owner_user_id or "anon",
            str(index_version),
            prompt_version,
            policy,
            normalize_query(query),
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
