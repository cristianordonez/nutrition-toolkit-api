from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine

from engine.models.sql.person import Person
from engine.repositories.person_repo import PersonRepo


def test_person_lookup_supports_all_three_identity_paths() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    birth_date = date(1940, 1, 2)

    with Session(engine) as session:
        person = Person(name="Doe, Jane", date_of_birth=birth_date)
        repository = PersonRepo(session)
        person = repository.create(person)
        repository.assign_identifier(person, " R-1 ")

        by_id = repository.get_by_id(person.id)  # ty: ignore[invalid-argument-type]
        by_identifier = repository.get_by_identifier("R-1")
        by_natural_identity = repository.get_by_name_and_birth_date(
            " jane ",
            "DOE",
            birth_date,
        )
        assert by_id is not None
        assert by_id.id == person.id
        assert by_identifier is not None
        assert by_identifier.id == person.id
        assert by_natural_identity is not None
        assert by_natural_identity.id == person.id


def test_one_identifier_cannot_name_two_people() -> None:
    """An identifier identifies exactly one resident.

    It used to be scoped by facility, because the same chart number could
    legitimately recur at two facilities. With no facility to scope by, a
    second claim on an identifier is a collision and has to be refused rather
    than silently producing two residents that lookups cannot tell apart.
    """
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = PersonRepo(session)
        jane = repository.create(Person(name="Doe, Jane"))
        john = repository.create(Person(name="Smith, John"))
        repository.assign_identifier(jane, "SHARED")

        with pytest.raises(ValueError, match="belongs to another person"):
            repository.assign_identifier(john, "SHARED")

        resolved = repository.get_by_identifier("SHARED")
        assert resolved is not None
        assert resolved.name == "Doe, Jane"


def test_identifier_is_stored_directly_on_person() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    inspector = inspect(engine)

    assert "person_external_identifier" not in inspector.get_table_names()
    assert "person_identifier" in {
        column["name"] for column in inspector.get_columns("person")
    }


def test_create_reuses_exact_natural_identity_not_name_only() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    repository_birth_date = date(1940, 1, 2)

    with Session(engine) as session:
        repository = PersonRepo(session)
        first = repository.create(
            Person(name="Doe, Jane", date_of_birth=repository_birth_date),
        )
        reused = repository.create(
            Person(
                name="  DOE,   JANE ",
                date_of_birth=repository_birth_date,
                height_in=64,
            ),
        )
        different = repository.create(
            Person(name="Doe, Jane", date_of_birth=date(1941, 1, 2)),
        )

        assert reused.id == first.id
        assert reused.height_in == 64  # noqa: PLR2004
        assert different.id != first.id


def test_names_without_birth_date_are_not_deduplicated() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = PersonRepo(session)
        first = repository.create(Person(name="Doe, Jane"))
        second = repository.create(Person(name="Doe, Jane"))

        assert first.id != second.id
