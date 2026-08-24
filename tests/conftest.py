from __future__ import annotations

import importlib
import os
import sys
import types
import typing
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ntk.services.api_key_service import APIKeyService

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from ntk.models.sql.api_key import APIKey, Permission
    from ntk.repositories.api_key_repo import APIKeyRepo
    from ntk.repositories.permission_repo import PermissionRepo


class FakeAPIKeyRepo:
    def __init__(self, api_keys: dict[str, APIKey] | None = None) -> None:
        self._api_keys = api_keys or {}
        self.updated_last_used: list[APIKey] = []
        self.created: list[APIKey] = []

    def get_by_hash(self, api_key_hash: str) -> APIKey | None:
        if api_key_hash in self._api_keys:
            return self._api_keys[api_key_hash]
        if len(self._api_keys) == 1:
            return next(iter(self._api_keys.values()))
        return None

    def revoke(self, api_key_hash: str) -> APIKey | None:
        api_key = self.get_by_hash(api_key_hash)
        if api_key is None:
            return None
        api_key.active = False
        api_key.revoked_at = datetime.now(UTC)
        return api_key

    def create(self, api_key: APIKey) -> APIKey:
        self._api_keys[api_key.api_key_hash] = api_key
        self.created.append(api_key)
        return api_key

    def get_all(self) -> list[APIKey]:
        return list(self._api_keys.values())

    def update_last_used(self, api_key: APIKey) -> None:
        api_key.last_used_at = datetime.now(UTC)
        self.updated_last_used.append(api_key)


class FakePermissionRepo:
    def __init__(self, permissions: list[Permission] | None = None) -> None:
        self._permissions = {
            permission.name: permission for permission in permissions or []
        }
        self.added_permissions: list[tuple[UUID, UUID]] = []
        self.removed_permissions: list[tuple[UUID, UUID]] = []

    def get_by_name(self, name: str) -> Permission | None:
        return self._permissions.get(name)

    def get_by_names(self, names: list[str]) -> list[Permission]:
        return [
            permission for name in names if (permission := self._permissions.get(name))
        ]

    def add_permission_to_api_key(self, api_key_id: UUID, permission_id: UUID) -> None:
        self.added_permissions.append((api_key_id, permission_id))

    def remove_permission_from_api_key(
        self,
        api_key_id: UUID,
        permission_id: UUID,
    ) -> None:
        self.removed_permissions.append((api_key_id, permission_id))


@pytest.fixture
def build_api_key_service() -> Callable[
    ...,
    APIKeyService,
]:
    def _build_service(
        *,
        api_keys: dict[str, APIKey] | None = None,
        permissions: list[Permission] | None = None,
    ) -> APIKeyService:
        api_key_repo = FakeAPIKeyRepo(api_keys)
        typed_key_repo = typing.cast("APIKeyRepo", api_key_repo)
        permission_repo = FakePermissionRepo(permissions)
        typed_permission_repo = typing.cast("PermissionRepo", permission_repo)
        return APIKeyService(typed_key_repo, typed_permission_repo)

    return _build_service


@pytest.fixture
def load_controller_module(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[str], typing.Any]:
    """Load controller modules with a lightweight database stub."""
    os.environ.setdefault("NTK_API_KEY", "test-api-key")
    os.environ.setdefault("DATABASE_USER", "test-user")
    os.environ.setdefault("DATABASE_HOST", "localhost")
    os.environ.setdefault("DATABASE_NAME", "test-db")
    os.environ.setdefault("DATABASE_PASSWORD", "test-password")
    db_module: typing.Any = types.ModuleType("ntk.database.db")
    db_module.get_session = lambda: iter([object()])
    monkeypatch.setitem(sys.modules, "ntk.database.db", db_module)

    def _load(module_name: str) -> types.ModuleType:
        sys.modules.pop(module_name, None)
        return importlib.import_module(module_name)

    return _load


@pytest.fixture
def patch_key_controller_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., dict[str, list[tuple[object, str]]]]:
    """Patch key controller dependencies with lightweight test doubles."""

    def _patch(
        module: typing.Any,  # noqa: ANN401
        *,
        api_keys: list[SimpleNamespace] | None = None,
        revoked_key: SimpleNamespace | None = None,
    ) -> dict[str, list[tuple[object, str]]]:
        calls: dict[str, list[tuple[object, str]]] = {
            "created": [],
            "granted": [],
            "revoked": [],
        }

        class FakeAPIKeyService:
            def __init__(self, repo: object, permission_repo: object) -> None:
                self.repo = repo
                self.permission_repo = permission_repo

            def create(self, name: str, permissions: list[str]) -> str:
                calls["created"].append((name, permissions[0]))
                return "generated-key"

            def get_api_keys(
                self,
                _: str | None = None,
                **__: object,
            ) -> list[SimpleNamespace]:
                if api_keys is None:
                    return []
                return api_keys

            def grant_permission(self, api_key: object, permission: str) -> None:
                calls["granted"].append((api_key, permission))

            def revoke_permission(self, api_key: object, permission: str) -> None:
                calls["revoked"].append((api_key, permission))

            def revoke_api_key(self, _: str) -> SimpleNamespace | None:
                return revoked_key

        monkeypatch.setattr(module, "get_session", lambda: iter([object()]))
        monkeypatch.setattr(module, "APIKeyRepo", lambda session: session)
        monkeypatch.setattr(module, "PermissionRepo", lambda session: session)
        monkeypatch.setattr(module, "APIKeyService", FakeAPIKeyService)
        return calls

    return _patch
