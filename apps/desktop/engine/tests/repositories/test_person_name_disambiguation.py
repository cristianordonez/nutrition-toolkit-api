"""Resolving same-name residents when identity is only partly known.

A stored record with no date of birth is compatible with any date, because
unknown contradicts nothing. That is right for asking "could this be them",
but it made two same-name records ambiguous the moment one lacked a birth
date -- even when the other matched exactly, which is what a document
supplying a date of birth should be able to settle.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

from engine.models.sql.person import Person
from engine.repositories.person_repo import PersonRepo

_BIRTH_DATE = date(1982, 7, 20)


def _session() -> Session:
    db = create_engine("sqlite://")
    SQLModel.metadata.create_all(db)
    return Session(db)


def test_a_birth_date_resolves_a_record_that_has_none() -> None:
    """The reported failure: one record dated, its duplicate not."""
    with _session() as session:
        repository = PersonRepo(session)
        dated = repository.create(
            Person(name="Diawatan, Mark", date_of_birth=_BIRTH_DATE),
        )
        repository.create(Person(name="Diawatan, Mark"))

        found = repository.get_compatible_by_name(
            "Mark",
            "Diawatan",
            birth_date=_BIRTH_DATE,
        )

        assert found is not None
        assert found.id == dated.id


def test_an_identifier_resolves_a_record_that_has_none() -> None:
    """The same reasoning applies to the identifier."""
    with _session() as session:
        repository = PersonRepo(session)
        identified = repository.create(
            Person(name="Diawatan, Mark", person_identifier="03526134"),
        )
        repository.create(Person(name="Diawatan, Mark"))

        found = repository.get_compatible_by_name(
            "Mark",
            "Diawatan",
            person_identifier="03526134",
        )

        assert found is not None
        assert found.id == identified.id


def test_nothing_to_go_on_still_reports_ambiguity() -> None:
    """Two same-name residents and no other evidence must not be guessed at."""
    with _session() as session:
        repository = PersonRepo(session)
        repository.create(Person(name="Diawatan, Mark"))
        repository.create(Person(name="Diawatan, Mark", person_identifier="X1"))

        with pytest.raises(LookupError, match="ambiguous"):
            repository.get_compatible_by_name("Mark", "Diawatan")


def test_name_and_birth_date_are_unique_together() -> None:
    """Why a known birth date settles the question for good.

    The schema will not hold two residents with the same name and the same
    date of birth, so once a date is known it identifies at most one record.
    The ambiguity this module fixes can therefore only arise between records
    where at least one has no date -- exactly the case that was failing.
    """
    with _session() as session:
        repository = PersonRepo(session)
        repository.create(
            Person(name="Diawatan, Mark", date_of_birth=_BIRTH_DATE),
        )

        duplicate = Person(
            name="Diawatan, Mark",
            date_of_birth=_BIRTH_DATE,
            person_identifier="OTHER",
        )
        repository._normalize_person(duplicate)  # noqa: SLF001
        session.add(duplicate)

        with pytest.raises(IntegrityError):
            session.commit()


def test_a_different_birth_date_is_a_different_person() -> None:
    """Narrowing must not turn a contradiction into a match."""
    with _session() as session:
        repository = PersonRepo(session)
        repository.create(
            Person(name="Diawatan, Mark", date_of_birth=_BIRTH_DATE),
        )

        found = repository.get_compatible_by_name(
            "Mark",
            "Diawatan",
            birth_date=date(1990, 1, 1),
        )

        assert found is None, "a new person should be created instead"


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        # As a hospital discharge packet headers every page.
        ("MRN 03526134", "03526134"),
        ("MRN: 03526134", "03526134"),
        ("mrn 03526134", "03526134"),
        ("MR# 12345", "12345"),
        ("Medical Record Number: 999", "999"),
        # Values, not labelled ones: these must survive untouched.
        ("03526134", "03526134"),
        ("EN140056", "EN140056"),
        ("MR12345", "MR12345"),
        ("  06353  ", "06353"),
    ],
)
def test_a_record_number_label_is_not_part_of_the_identifier(
    printed: str,
    expected: str,
) -> None:
    """One document writes the number three ways; all are the same person.

    Keeping the label split one resident into two records, and the next
    document matching both by name then refused to load because the two
    disagreed.
    """
    assert PersonRepo._normalize_identifier(printed) == expected  # noqa: SLF001


def test_a_labelled_identifier_finds_the_person_stored_without_the_label() -> None:
    with _session() as session:
        repository = PersonRepo(session)
        stored = repository.create(
            Person(
                name="Diawatan, Mark",
                date_of_birth=_BIRTH_DATE,
                person_identifier="03526134",
            ),
        )

        found = repository.get_by_identifier("MRN 03526134")

        assert found is not None
        assert found.id == stored.id
