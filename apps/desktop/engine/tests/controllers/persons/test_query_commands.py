from __future__ import annotations

import argparse
import typing
from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, create_engine

from engine.controllers.persons import weights
from engine.controllers.persons.app import PersonControllerGroup
from engine.controllers.persons.ncps import (
    PersonNCPsController,
    PersonNCPsOptions,
)
from engine.controllers.persons.weights import (
    PersonWeightsController,
    PersonWeightsOptions,
)
from engine.models.clinical_facts import PersonWeight
from engine.models.ncp_note import NCPNoteStatus, NCPNoteType
from engine.models.sql.ncp_note import NCPNote
from engine.models.sql.person import Person
from engine.repositories.person_repo import PersonRepo

if typing.TYPE_CHECKING:
    import pytest


def test_person_group_registers_plural_query_commands() -> None:
    person_id = 42
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    PersonControllerGroup().register(subparsers)

    ncps_args = parser.parse_args(
        ["persons", "ncps", "--person-identifier", "person-42"],
    )
    weight_args = parser.parse_args(
        ["persons", "weights", "--person-ids", str(person_id)],
    )

    assert ncps_args.command == "persons"
    assert ncps_args.persons_command == "ncps"
    assert ncps_args.person_identifier == "person-42"
    assert weight_args.persons_command == "weights"
    assert weight_args.person_ids == [person_id]


def test_person_ncps_command_reads_local_storage() -> None:
    """Notes now live only on this device, so no network call is made."""
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        person = PersonRepo(session).create(
            Person(name="Cai, Test", person_identifier="person-42"),
        )
        session.add(
            NCPNote(
                person_id=person.id,
                note_type=NCPNoteType.QUARTERLY,
                content="Assessment",
                status=NCPNoteStatus.FINALIZED,
                finalized_at=datetime(2026, 8, 28, tzinfo=UTC),
            ),
        )
        session.commit()

        output = PersonNCPsController(session=session).run(
            PersonNCPsOptions(person_identifier="person-42"),
        )

    assert [note.content for note in output.result.ncps] == ["Assessment"]
    assert '"content": "Assessment"' in output.result.to_console()


def test_person_ncps_command_reports_an_unknown_person_as_empty() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        output = PersonNCPsController(session=session).run(
            PersonNCPsOptions(person_identifier="nobody"),
        )

    assert output.result.ncps == []


def test_person_weights_command_queries_requested_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    person_id = 42
    weight = PersonWeight(
        person_id=person_id,
        measured_at=datetime(2026, 8, 28, tzinfo=UTC),
        weight_lb=150,
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        def get_weights_by_person_ids(
            person_ids: list[int],
        ) -> list[PersonWeight]:
            assert person_ids == [person_id]
            return [weight]

    monkeypatch.setattr(weights, "PersonRepo", Repository)

    output = PersonWeightsController(
        session="session",  # ty: ignore[invalid-argument-type]
    ).run(PersonWeightsOptions(person_ids=[person_id]))

    assert output.result.weights == [weight]
    assert '"weight_lb": 150.0' in output.result.to_console()
