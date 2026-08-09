from __future__ import annotations

import typing

import pytest
from sqlmodel import Session, SQLModel, create_engine

from ntk.defaults import DEFAULT_PERMISSIONS
from ntk.models import APIKey, APIKeyPermission, Permission
from ntk.repositories.permission_repo import PermissionRepo


@pytest.fixture
def session() -> typing.Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_get_by_name_returns_permission(session: Session) -> None:
    permission = Permission(name="read")
    session.add(permission)
    session.commit()
    repo = PermissionRepo(session)
    assert repo.get_by_name("read") is permission


def test_get_by_names_returns_matching_permissions(session: Session) -> None:
    read_permission = Permission(name="read")
    write_permission = Permission(name="write")
    session.add_all([read_permission, write_permission])
    session.commit()
    repo = PermissionRepo(session)
    assert repo.get_by_names(["read", "write"]) == [read_permission, write_permission]


def test_list_all_returns_all_permissions(session: Session) -> None:
    permissions = [Permission(name=name) for name in ["read", "write"]]
    session.add_all(permissions)
    session.commit()
    repo = PermissionRepo(session)
    assert repo.list_all() == permissions


def test_create_persists_permission(session: Session) -> None:
    repo = PermissionRepo(session)
    created = repo.create(Permission(name="read"))
    assert created.name == "read"
    assert repo.get_by_name("read") is created


def test_seed_defaults_adds_missing_permissions(session: Session) -> None:
    repo = PermissionRepo(session)
    repo.seed_defaults()
    seeded_names = {permission.name for permission in repo.list_all()}
    assert seeded_names >= set(DEFAULT_PERMISSIONS)


def test_add_permission_to_api_key_persists_link(session: Session) -> None:
    api_key = APIKey(name="demo", api_key_hash="hash", permissions=[])
    permission = Permission(name="read")
    session.add_all([api_key, permission])
    session.commit()
    repo = PermissionRepo(session)
    repo.add_permission_to_api_key(api_key.id, permission.id)
    link = session.get(APIKeyPermission, (api_key.id, permission.id))
    assert link is not None


def test_remove_permission_from_api_key_deletes_link(session: Session) -> None:
    api_key = APIKey(name="demo", api_key_hash="hash", permissions=[])
    permission = Permission(name="read")
    session.add_all([api_key, permission])
    session.commit()
    repo = PermissionRepo(session)
    repo.add_permission_to_api_key(api_key.id, permission.id)
    repo.remove_permission_from_api_key(api_key.id, permission.id)
    link = session.get(APIKeyPermission, (api_key.id, permission.id))
    assert link is None
