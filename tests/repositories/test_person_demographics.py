from __future__ import annotations

from datetime import date

from sqlmodel import Session, SQLModel, create_engine

import ntk.models.sql  # noqa: F401
from ntk.models.sql.person import Person
from ntk.repositories.person_repo import PersonRepo

_HEIGHT_IN = 64.5


def test_person_can_be_created_with_demographics() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        person = PersonRepo(session).create(
            Person(
                name="Person",
                date_of_birth=date(1946, 2, 1),
                sex="Female",
                height_in=_HEIGHT_IN,
            ),
        )

        assert person.date_of_birth == date(1946, 2, 1)
        assert person.sex == "f"
        assert person.height_in == _HEIGHT_IN


def test_person_demographics_can_be_omitted() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        person = PersonRepo(session).create(Person(name="Person"))

        assert person.date_of_birth is None
        assert person.sex is None
        assert person.height_in is None


def test_later_null_demographics_do_not_replace_existing_values() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = PersonRepo(session)
        original = repository.create(
            Person(
                name="Person",
                date_of_birth=date(1946, 2, 1),
                sex="f",
                height_in=_HEIGHT_IN,
            ),
        )

        imported_again = repository.update_demographics(
            original,
        )

        assert imported_again.id == original.id
        assert imported_again.date_of_birth == date(1946, 2, 1)
        assert imported_again.sex == "f"
        assert imported_again.height_in == _HEIGHT_IN


def test_later_non_null_demographics_populate_missing_values() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = PersonRepo(session)
        original = repository.create(Person(name="Person"))

        imported_again = repository.update_demographics(
            original,
            date_of_birth=date(1946, 2, 1),
            sex="Female",
            height_in=_HEIGHT_IN,
        )

        assert imported_again.id == original.id
        assert imported_again.date_of_birth == date(1946, 2, 1)
        assert imported_again.sex == "f"
        assert imported_again.height_in == _HEIGHT_IN
