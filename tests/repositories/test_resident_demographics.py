from __future__ import annotations

from datetime import date

from sqlmodel import Session, SQLModel, create_engine

import ntk.models.sql  # noqa: F401
from ntk.models.sql.resident import Resident
from ntk.repositories.resident_repo import ResidentRepo

_HEIGHT_IN = 64.5


def test_resident_can_be_created_with_demographics() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        resident = ResidentRepo(session).create(
            Resident(
                name="Resident",
                date_of_birth=date(1946, 2, 1),
                sex="Female",
                height_in=_HEIGHT_IN,
            ),
        )

        assert resident.date_of_birth == date(1946, 2, 1)
        assert resident.sex == "f"
        assert resident.height_in == _HEIGHT_IN


def test_resident_demographics_can_be_omitted() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        resident = ResidentRepo(session).create(Resident(name="Resident"))

        assert resident.date_of_birth is None
        assert resident.sex is None
        assert resident.height_in is None


def test_later_null_demographics_do_not_replace_existing_values() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = ResidentRepo(session)
        original = repository.create(
            Resident(
                name="Resident",
                date_of_birth=date(1946, 2, 1),
                sex="f",
                height_in=_HEIGHT_IN,
            ),
        )

        imported_again = repository.create(Resident(name="Resident"))

        assert imported_again.id == original.id
        assert imported_again.date_of_birth == date(1946, 2, 1)
        assert imported_again.sex == "f"
        assert imported_again.height_in == _HEIGHT_IN


def test_later_non_null_demographics_populate_missing_values() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = ResidentRepo(session)
        original = repository.create(Resident(name="Resident"))

        imported_again = repository.create(
            Resident(
                name="Resident",
                date_of_birth=date(1946, 2, 1),
                sex="Female",
                height_in=_HEIGHT_IN,
            ),
        )

        assert imported_again.id == original.id
        assert imported_again.date_of_birth == date(1946, 2, 1)
        assert imported_again.sex == "f"
        assert imported_again.height_in == _HEIGHT_IN
