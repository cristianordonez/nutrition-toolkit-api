from __future__ import annotations

import asyncio
import typing
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

if typing.TYPE_CHECKING:
    from collections.abc import Callable

_UNAUTHORIZED = 401


class FakeAPIKey:
    name = "client"
    id = "key-id"

    def __init__(self, permissions: set[str]) -> None:
        self.permissions = permissions

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions


def test_verify_api_key_authenticates_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
    load_controller_module: Callable[[str], typing.Any],
) -> None:
    middleware = load_controller_module("ntk.presentation.api.middleware")
    expected = SimpleNamespace(name="client")

    class Service:
        def authenticate(self, api_key: str) -> object:
            assert api_key == "secret"
            return expected

    monkeypatch.setattr(middleware, "get_api_key_service", Service)

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="secret")
    result = asyncio.run(middleware.verify_api_key(credentials))

    assert result is expected


def test_verify_api_key_rejects_missing_authorization_header(
    load_controller_module: Callable[[str], typing.Any],
) -> None:
    middleware = load_controller_module("ntk.presentation.api.middleware")
    with pytest.raises(HTTPException, match="Missing Authorization header") as exc_info:
        asyncio.run(middleware.verify_api_key(None))

    assert exc_info.value.status_code == _UNAUTHORIZED


def test_permission_dependencies_accept_and_reject_permissions(
    load_controller_module: Callable[[str], typing.Any],
) -> None:
    middleware = load_controller_module("ntk.presentation.api.middleware")
    key = FakeAPIKey({"read"})

    assert asyncio.run(middleware.require_permission("read")(key)) is key
    assert asyncio.run(middleware.require_any_permission(["write", "read"])(key)) is key

    with pytest.raises(HTTPException, match="Permission 'write' required"):
        asyncio.run(middleware.require_permission("write")(key))
    with pytest.raises(HTTPException, match="At least one"):
        asyncio.run(middleware.require_any_permission(["write", "admin"])(key))


def test_rate_limit_tracks_and_rejects_excess_requests(
    monkeypatch: pytest.MonkeyPatch,
    load_controller_module: Callable[[str], typing.Any],
) -> None:
    middleware = load_controller_module("ntk.presentation.api.middleware")

    class Redis:
        def __init__(self) -> None:
            self.count = 0
            self.expirations: list[tuple[str, int]] = []

        async def incr(self, _: str) -> int:
            self.count += 1
            return self.count

        async def expire(self, key: str, window: int) -> None:
            self.expirations.append((key, window))

    redis = Redis()
    monkeypatch.setattr(middleware, "redis", redis)
    limiter = middleware.rate_limit(1, window=30, scope="test-route")
    key = FakeAPIKey(set())

    asyncio.run(limiter(key))
    assert redis.expirations == [("rate_limit:test-route:client-key-id", 30)]
    with pytest.raises(HTTPException, match="Rate limit exceeded"):
        asyncio.run(limiter(key))


def test_verify_api_key_rejects_invalid_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
    load_controller_module: Callable[[str], typing.Any],
) -> None:
    middleware = load_controller_module("ntk.presentation.api.middleware")

    class Service:
        def authenticate(self, _: str) -> object:
            msg = "Invalid API key"
            raise ValueError(msg)

    monkeypatch.setattr(middleware, "get_api_key_service", Service)

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="invalid",
    )
    with pytest.raises(HTTPException, match="Invalid or expired API key") as exc_info:
        asyncio.run(middleware.verify_api_key(credentials))

    assert exc_info.value.status_code == _UNAUTHORIZED


def test_get_api_key_service_builds_repositories(
    monkeypatch: pytest.MonkeyPatch,
    load_controller_module: Callable[[str], typing.Any],
) -> None:
    middleware = load_controller_module("ntk.presentation.api.middleware")
    session = object()
    monkeypatch.setattr(middleware, "get_session", lambda: iter([session]))
    monkeypatch.setattr(
        middleware,
        "APIKeyRepo",
        lambda value: ("api-keys", value),
    )
    monkeypatch.setattr(
        middleware,
        "PermissionRepo",
        lambda value: ("permissions", value),
    )
    monkeypatch.setattr(
        middleware,
        "APIKeyService",
        lambda api_keys, permissions: (api_keys, permissions),
    )

    assert middleware.get_api_key_service() == (
        ("api-keys", session),
        ("permissions", session),
    )
