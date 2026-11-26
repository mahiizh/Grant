from qdrant_client import models

from app.core.acl import ACLScope
from app.retrieval.filters import RetrievalFilter


def _bob_filter(**overrides: object) -> RetrievalFilter:
    values: dict[str, object] = {
        "acl_scope": ACLScope.owner("bob"),
        "owner_user_id": "bob",
    }
    values.update(overrides)
    return RetrievalFilter(**values)


def test_qdrant_filter_pushes_owner_and_public_alternatives() -> None:
    qdrant_filter = _bob_filter().to_qdrant_filter()

    assert qdrant_filter.must is not None
    nested = [c for c in qdrant_filter.must if isinstance(c, models.Filter)]
    assert len(nested) == 1
    assert nested[0].should is not None
    keys = {getattr(c, "key", None) for c in nested[0].should}
    assert {
        "owner_user_id",
        "acl_scope.owner_user_id",
        "acl_scope.is_public",
        "acl_is_public",
    } <= keys
    assert "acl_scope.shared_scope" not in keys

    shared_filter = _bob_filter(acl_scope=ACLScope.shared("shared-operations"))
    shared_nested = [
        c
        for c in shared_filter.to_qdrant_filter().must or []
        if isinstance(c, models.Filter)
    ]
    shared_keys = {getattr(c, "key", None) for c in shared_nested[0].should or []}
    assert "acl_scope.shared_scope" in shared_keys


def test_qdrant_filter_includes_doc_ids_without_temporal_bounds() -> None:
    qdrant_filter = _bob_filter(
        doc_ids=frozenset({"doc_shared_ops"}),
    ).to_qdrant_filter()

    dumped = qdrant_filter.model_dump_json()
    assert "doc_shared_ops" in dumped
    assert "valid_from" not in dumped
    assert "valid_to" not in dumped
    assert "as_of" not in dumped


def test_qdrant_filter_admin_skips_acl_should_group() -> None:
    qdrant_filter = _bob_filter(is_admin=True).to_qdrant_filter()
    assert not any(isinstance(c, models.Filter) for c in qdrant_filter.must or [])


def test_cypher_predicate_is_parameterized_for_owner_shared() -> None:
    clause, params = _bob_filter().to_cypher_predicate("n")

    assert "$acl_owner_user_id" in clause
    assert "$acl_shared_scope" in clause
    assert "$acl_is_admin" in clause
    assert "n.owner_user_id" in clause
    assert "n.shared_scope" in clause
    assert "acl_allowed_roles" not in clause
    assert "n.tenant_id = '" not in clause
    assert params["acl_owner_user_id"] == "bob"
    assert params["acl_shared_scope"] is None
    assert params["acl_is_admin"] is False


def test_permits_payload_default_denies_missing_or_legacy_restricted_acl() -> None:
    bob = _bob_filter()

    assert not bob.permits_payload({"doc_id": "doc_a", "text": "no acl"})
    assert not bob.permits_payload({"acl_scope": {}, "doc_id": "doc_a"})
    assert bob.permits_payload(
        {
            "acl_scope": {"is_public": True},
            "doc_id": "doc_a",
        }
    )
    assert bob.permits_payload(
        {
            "acl_scope": {"owner_user_id": "bob"},
            "owner_user_id": "bob",
            "doc_id": "doc_b",
        }
    )
    assert not bob.permits_payload(
        {
            "acl_scope": {
                "tenant_id": "default",
                "is_public": False,
                "allowed_roles": ["data-platform"],
                "allowed_groups": [],
            },
            "doc_id": "doc_c",
        }
    )


def test_permits_payload_accepts_modern_public_dump_with_top_level_owner() -> None:
    alice = _bob_filter(acl_scope=ACLScope.public(), owner_user_id="alice")
    bob = _bob_filter()
    payload = {
        "doc_id": "doc_a",
        "owner_user_id": "alice",
        "acl_scope": {"owner_user_id": None, "shared_scope": None},
    }

    assert alice.permits_payload(payload)
    assert not bob.permits_payload(payload)
