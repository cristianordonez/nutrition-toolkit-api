from __future__ import annotations

from sqlalchemy import Integer, String
from sqlmodel import Session, SQLModel, create_engine

from ntk.models.sql.user import User, UserHash


def test_user_hash_schema_and_persistence() -> None:
    expected_hash_length = 350
    table = UserHash.__table__  # ty: ignore[unresolved-attribute]

    assert set(table.c.keys()) == {"id", "user_id", "hash"}
    assert isinstance(table.c.id.type, Integer)
    assert isinstance(table.c.hash.type, String)
    assert table.c.hash.type.length == expected_hash_length
    assert {key.target_fullname for key in table.c.user_id.foreign_keys} == {
        "user.id",
    }

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    user = User(
        name="User",
        email="user@example.com",
    )
    user_hash = UserHash(user_id=0, user=user, hash="test-hash")

    with Session(engine) as session:
        session.add_all([user, user_hash])
        session.commit()
        session.refresh(user_hash)

        assert user_hash.id == 1
