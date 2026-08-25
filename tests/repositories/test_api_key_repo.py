from __future__ import annotations

import typing
from datetime import UTC, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

from ntk.models.sql.api_key import APIKey
from ntk.repositories.api_key_repo import APIKeyRepo


@pytest.fixture
def session() -> typing.Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_create_persists_api_key(session: Session) -> None:
    repo = APIKeyRepo(session)
    api_key = APIKey(name="demo", api_key_hash="hash", permissions=[])
    created = repo.create(api_key)
    assert created is api_key
    assert repo.get_by_hash("hash") is api_key


def test_get_by_hash_returns_matching_key(session: Session) -> None:
    repo = APIKeyRepo(session)
    api_key = APIKey(name="demo", api_key_hash="hash", permissions=[])
    session.add(api_key)
    session.commit()
    assert repo.get_by_hash("hash") is api_key
    assert repo.get_by_hash("missing") is None


def test_get_all_returns_all_keys(session: Session) -> None:
    repo = APIKeyRepo(session)
    api_keys = [
        APIKey(name="demo-1", api_key_hash="hash-1", permissions=[]),
        APIKey(name="demo-2", api_key_hash="hash-2", permissions=[]),
    ]
    session.add_all(api_keys)
    session.commit()
    assert repo.get_all() == api_keys


def test_get_by_name_returns_matching_key(session: Session) -> None:
    repo = APIKeyRepo(session)
    api_key = APIKey(name="demo", api_key_hash="hash", permissions=[])
    session.add(api_key)
    session.commit()
    assert repo.get_by_name("demo") is api_key
    assert repo.get_by_name("missing") is None


def test_revoke_marks_key_as_revoked(session: Session) -> None:
    repo = APIKeyRepo(session)
    api_key = APIKey(name="demo", api_key_hash="hash", permissions=[])
    session.add(api_key)
    session.commit()
    revoked = repo.revoke("hash")
    assert revoked is api_key
    assert api_key.active is False
    assert api_key.revoked_at is not None


def test_update_last_used_sets_timestamp(session: Session) -> None:
    repo = APIKeyRepo(session)
    api_key = APIKey(name="demo", api_key_hash="hash", permissions=[])
    session.add(api_key)
    session.commit()
    repo.update_last_used(api_key)
    assert api_key.last_used_at is not None
    assert api_key.last_used_at.year == datetime.now(tz=UTC).year
    assert api_key.last_used_at.month == datetime.now(tz=UTC).month
    assert api_key.last_used_at.day == datetime.now(tz=UTC).day
