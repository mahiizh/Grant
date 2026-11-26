import pytest
from fastapi import HTTPException

from app.core.acl import ACLScope
from app.core.auth import AuthenticatedUser
from app.core.config import get_settings


def _user(username: str) -> AuthenticatedUser:
    return AuthenticatedUser(username, get_settings().DEV_USERS[username])


@pytest.mark.parametrize(
    ("username", "user_id"),
    [
        ("alice", "usr_alice_01"),
        ("bob", "usr_bob_02"),
        ("elena", "usr_elena_03"),
        ("dave", "usr_dave_04"),
        ("auditor", "usr_auditor_05"),
    ],
)
def test_default_scope_is_owner_private(username: str, user_id: str) -> None:
    user = _user(username)
    assert {user.resolve_scope() for _ in range(25)} == {None}

    scope = user.to_acl_scope()
    assert scope.owner_user_id == user_id
    assert scope.shared_scope is None


def test_admin_default_scope_is_public_but_keeps_admin_flag() -> None:
    user = _user("admin")
    assert user.to_acl_scope() == ACLScope.public()
    assert user.to_retrieval_filter().is_admin is True


def test_bob_cannot_request_ungranted_shared_scope() -> None:
    with pytest.raises(HTTPException) as exc:
        _user("bob").to_acl_scope("shared-analytics")
    assert exc.value.status_code == 403


def test_public_is_not_a_requestable_shared_scope() -> None:
    with pytest.raises(HTTPException) as exc:
        _user("bob").to_retrieval_filter("public")
    assert exc.value.status_code == 403


def test_retrieval_filter_carries_owner_identity() -> None:
    retrieval_filter = _user("bob").to_retrieval_filter()

    assert retrieval_filter.owner_user_id == "usr_bob_02"
    assert retrieval_filter.acl_scope == ACLScope.owner("usr_bob_02")
    assert retrieval_filter.is_admin is False


def test_requested_shared_scope_is_validated_and_carried() -> None:
    retrieval_filter = _user("bob").to_retrieval_filter("shared-operations")

    assert retrieval_filter.acl_scope == ACLScope.shared("shared-operations")
    assert retrieval_filter.owner_user_id == "usr_bob_02"
    assert retrieval_filter.is_admin is False
