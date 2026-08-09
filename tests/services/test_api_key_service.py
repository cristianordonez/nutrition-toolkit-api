from __future__ import annotations

import typing
from datetime import UTC, datetime, timedelta

import pytest

from ntk.models.api_key import APIKey, Permission

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from ntk.services.api_key_service import APIKeyService


def test_authenticate_returns_key_and_updates_last_used(
    build_api_key_service: Callable[
        ...,
        APIKeyService,
    ],
) -> None:
    plaintext_key = "plaintext-key"
    api_key = APIKey(name="demo", api_key_hash="hash", permissions=[])
    service = build_api_key_service(api_keys={"hash": api_key})
    result = service.authenticate(plaintext_key)
    assert result is api_key
    assert service.api_key_repo.updated_last_used == [api_key]  # ty: ignore[unresolved-attribute]
    assert api_key.last_used_at is not None


def test_authenticate_raises_for_expired_api_key(
    build_api_key_service: Callable[..., APIKeyService],
) -> None:
    plaintext_key = "plaintext-key"
    expired_key = APIKey(
        name="demo",
        api_key_hash="hash",
        permissions=[],
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    service = build_api_key_service(api_keys={"hash": expired_key})
    with pytest.raises(ValueError, match="expired"):
        service.authenticate(plaintext_key)


def test_revoke_api_key_marks_key_as_revoked(
    build_api_key_service: Callable[..., APIKeyService],
) -> None:
    plaintext_key = "plaintext-key"
    api_key = APIKey(name="demo", api_key_hash="hash", permissions=[])
    service = build_api_key_service(api_keys={"hash": api_key})
    revoked_key = service.revoke_api_key(plaintext_key)
    assert revoked_key is api_key
    assert api_key.active is False
    assert api_key.revoked_at is not None


def test_get_api_keys_returns_matching_key_when_filtered(
    build_api_key_service: Callable[..., APIKeyService],
) -> None:
    plaintext_key = "plaintext-key"
    api_key = APIKey(name="demo", api_key_hash="hash", permissions=[])
    service = build_api_key_service(api_keys={"hash": api_key})
    assert service.get_api_keys(plaintext_key) == [api_key]


def test_grant_permission_tracks_permission_assignment(
    build_api_key_service: Callable[..., APIKeyService],
) -> None:
    api_key = APIKey(name="demo", api_key_hash="hash", permissions=[])
    permission = Permission(name="read")
    service = build_api_key_service(permissions=[permission])
    service.grant_permission(api_key, "read")
    assert service.permission_repo.added_permissions == [(api_key.id, permission.id)]  # ty: ignore[unresolved-attribute]


def test_revoke_permission_tracks_permission_removal(
    build_api_key_service: Callable[..., APIKeyService],
) -> None:
    api_key = APIKey(name="demo", api_key_hash="hash", permissions=[])
    permission = Permission(name="read")
    service = build_api_key_service(permissions=[permission])
    service.revoke_permission(api_key, "read")
    assert service.permission_repo.removed_permissions == [(api_key.id, permission.id)]  # ty: ignore[unresolved-attribute]


def test_create_returns_plaintext_key_and_persists_api_key(
    build_api_key_service: Callable[..., APIKeyService],
) -> None:
    permission = Permission(name="read")
    service = build_api_key_service(permissions=[permission])
    plaintext_key = service.create("demo", ["read"])
    assert isinstance(plaintext_key, str)
    assert plaintext_key
    assert len(service.api_key_repo.created) == 1  # ty: ignore[unresolved-attribute]
    created_key = service.api_key_repo.created[0]  # ty: ignore[unresolved-attribute]
    assert created_key.name == "demo"
    assert created_key.permissions == [permission]


def test_create_raises_when_permissions_are_unknown(
    build_api_key_service: Callable[..., APIKeyService],
) -> None:
    service = build_api_key_service(permissions=[])

    with pytest.raises(ValueError, match="Provided permissions"):
        service.create("demo", ["read"])
