"""One resident recorded twice -- by facility ID, and by name and birth date."""

from __future__ import annotations

from datetime import date

import pytest
from sqlmodel import Session, select

from engine.database.bootstrap import upgrade_database
from engine.database.db import create_database_engine
from engine.models.ncp_note import NCPNoteType
from engine.models.sql.clinical_fact import ClinicalFact, ExtractionMethod
from engine.models.sql.ncp_note import NCPNote
from engine.models.sql.person import Person
from engine.repositories.person_repo import PersonRepo
from engine.services.person.person_service import PersonService
from engine.utils.misc import require_id

BIRTH_DATE = date(1941, 3, 9)


def _session() -> Session:
    database = create_database_engine("sqlite://")
    upgrade_database(database)
    return Session(database)


def _fact(person: Person, identity: str) -> ClinicalFact:
    return ClinicalFact(
        person_id=require_id(person.id),
        fact_type="weight",
        payload={"type": "weight"},
        identity_hash=identity,
        content_hash=identity,
        extraction_method=ExtractionMethod.DETERMINISTIC,
    )


def _two_records(session: Session) -> tuple[Person, Person]:
    """A PCC record with the ID only, and an outside record with the DOB only."""
    repository = PersonRepo(session)
    by_identifier = repository.create(
        Person(name="Example, Ada", person_identifier="EX1234"),
    )
    by_birth = repository.create(
        Person(name="Example, Ada", date_of_birth=BIRTH_DATE),
    )
    session.add_all(
        [
            _fact(by_identifier, "shared"),
            _fact(by_birth, "shared"),
            _fact(by_birth, "only-outside"),
            NCPNote(
                person_id=by_birth.id,
                note_type=NCPNoteType.QUARTERLY,
                content="draft",
            ),
        ],
    )
    session.commit()
    return by_identifier, by_birth


def test_a_pcc_report_joins_the_two_records_into_one() -> None:
    with _session() as session:
        by_identifier, by_birth = _two_records(session)
        keep_id, duplicate_id = by_identifier.id, by_birth.id

        resolved = PersonService(PersonRepo(session)).resolve_or_create_person(
            source_person_name="Example, Ada",
            source_person_identifier="EX1234",
            date_of_birth=BIRTH_DATE,
        )

        assert resolved.id == keep_id
        assert resolved.person_identifier == "EX1234"
        assert resolved.date_of_birth == BIRTH_DATE
        assert session.get(Person, duplicate_id) is None
        facts = session.exec(select(ClinicalFact)).all()
        assert {fact.person_id for fact in facts} == {keep_id}
        # The fact both held is kept once; the outside-only fact moved over.
        assert sorted(fact.identity_hash for fact in facts) == [
            "only-outside",
            "shared",
        ]
        note = session.exec(select(NCPNote)).one()
        assert note.person_id == keep_id


@pytest.mark.parametrize(
    "change",
    [
        "identifier record has a birth date",
        "birth record has an identifier",
        "names differ",
    ],
)
def test_real_disagreements_are_not_merged(change: str) -> None:
    with _session() as session:
        repository = PersonRepo(session)
        by_identifier = repository.create(
            Person(
                name="Example, Ada",
                person_identifier="EX1234",
                date_of_birth=(
                    date(1950, 1, 1)
                    if change == "identifier record has a birth date"
                    else None
                ),
            ),
        )
        repository.create(
            Person(
                name="Example, Ada" if change != "names differ" else "Example, Bea",
                date_of_birth=BIRTH_DATE,
                person_identifier=(
                    "OTHER9" if change == "birth record has an identifier" else None
                ),
            ),
        )

        with pytest.raises(ValueError, match="conflict"):
            PersonService(repository).resolve_or_create_person(
                source_person_name="Example, Ada"
                if change != "names differ"
                else "Example, Bea",
                source_person_identifier="EX1234",
                date_of_birth=BIRTH_DATE,
            )

        assert session.get(Person, by_identifier.id) is not None
        assert len(session.exec(select(Person)).all()) == 2  # noqa: PLR2004
