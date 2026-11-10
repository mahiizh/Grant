import pytest
from fastapi import HTTPException

from app.core.auth import AuthenticatedUser
from app.core.config import get_settings


def _user(username: str) -> AuthenticatedUser:
    return AuthenticatedUser(username, get_settings().DEV_USERS[username])


@pytest.mark.parametrize(
    ("username", "expected_scope"),
    [
        ("alice", "data-platform"),
        ("bob", "sre"),
        ("elena", "payments"),
        ("dave", "core-banking"),
        ("auditor", "executive-audit"),
        ("admin", "data-platform"),
    ],
)
def test_default_scope_is_deterministic(username: str, expected_scope: str) -> None:
    user = _user(username)
    # Repeat to catch set-iteration-order flakiness.
    assert {user.resolve_scope() for _ in range(25)} == {expected_scope}
    assert {user.to_acl_scope().tenant_id for _ in range(5)} == {"default"}


def test_bob_cannot_request_data_platform_scope() -> None:
    with pytest.raises(HTTPException) as exc:
        _user("bob").to_acl_scope("data-platform")
    assert exc.value.status_code == 403


def test_retrieval_filter_carries_granted_scope_as_role_and_group() -> None:
    retrieval_filter = _user("bob").to_retrieval_filter()
    assert "sre" in retrieval_filter.user_roles
    assert "sre" in retrieval_filter.user_groups
    assert retrieval_filter.acl_scope.is_public is False


def test_public_scope_filter_only_allows_public_payloads() -> None:
    retrieval_filter = _user("bob").to_retrieval_filter("public")
    assert retrieval_filter.acl_scope.is_public is True
    assert retrieval_filter.user_roles == frozenset()
    assert retrieval_filter.user_groups == frozenset()
