from datetime import UTC, datetime

from qdrant_client import models

from app.core.acl import ACLScope
from app.retrieval.filters import RetrievalFilter


def _bob_filter(**overrides: object) -> RetrievalFilter:
    values: dict[str, object] = {
        "acl_scope": ACLScope.restricted({"sre"}, {"sre"}),
        "user_roles": frozenset({"incident-commander", "sre-lead", "sre"}),
        "user_groups": frozenset({"sre"}),
    }
    values.update(overrides)
    return RetrievalFilter(**values)


def test_qdrant_filter_pushes_tenant_and_acl_or_group() -> None:
    qdrant_filter = _bob_filter().to_qdrant_filter()

    assert qdrant_filter.must is not None
    assert any(getattr(c, "key", None) == "acl_scope.tenant_id" for c in qdrant_filter.must)

    nested = [c for c in qdrant_filter.must if isinstance(c, models.Filter)]
    assert len(nested) == 1
    assert nested[0].should is not None
    keys = {getattr(c, "key", None) for c in nested[0].should}
    assert keys == {
        "acl_scope.is_public",
        "acl_scope.allowed_roles",
        "acl_scope.allowed_groups",
    }


def test_qdrant_filter_includes_doc_ids_and_temporal_bounds() -> None:
    qdrant_filter = _bob_filter(
        as_of_time=datetime(2026, 4, 1, tzinfo=UTC),
        doc_ids=frozenset({"doc_team_directory_2026"}),
    ).to_qdrant_filter()

    dumped = qdrant_filter.model_dump_json()
    assert "temporal.valid_from" in dumped
    assert "temporal.valid_to" in dumped
    assert "doc_team_directory_2026" in dumped


def test_qdrant_filter_admin_skips_acl_should_group() -> None:
    qdrant_filter = _bob_filter(is_admin=True).to_qdrant_filter()
    assert not any(isinstance(c, models.Filter) for c in qdrant_filter.must or [])


def test_cypher_predicate_is_parameterized_and_checks_roles() -> None:
    clause, params = _bob_filter().to_cypher_predicate("n")

    assert "$acl_tenant_id" in clause
    assert "$acl_user_roles" in clause
    assert "acl_allowed_roles" in clause
    # The old bug treated same-tenant as allowed; the predicate must not.
    assert "n.tenant_id = '" not in clause
    assert params["acl_tenant_id"] == "default"
    assert params["acl_user_roles"] == ["incident-commander", "sre", "sre-lead"]
    assert params["acl_is_admin"] is False


def test_permits_payload_default_denies_missing_acl() -> None:
    bob = _bob_filter()

    assert not bob.permits_payload({"doc_id": "doc_a", "text": "no acl"})
    assert not bob.permits_payload({"acl_scope": {}, "doc_id": "doc_a"})
    assert bob.permits_payload(
        {
            "acl_scope": {"tenant_id": "default", "is_public": True},
            "doc_id": "doc_a",
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
            "doc_id": "doc_b",
        }
    )
