from __future__ import annotations

import argparse
import typing
from datetime import UTC, datetime

from ntk.controllers.persons import assessments, weights
from ntk.controllers.persons.app import PersonControllerGroup
from ntk.controllers.persons.assessments import (
    PersonAssessmentsController,
    PersonAssessmentsOptions,
)
from ntk.controllers.persons.weights import (
    PersonWeightsController,
    PersonWeightsOptions,
)
from ntk.models.sql.person import PersonAssessment, PersonWeight

if typing.TYPE_CHECKING:
    import pytest


def test_person_group_registers_plural_query_commands() -> None:
    person_id = 42
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    PersonControllerGroup().register(subparsers)

    assessment_args = parser.parse_args(
        ["persons", "assessments", "--person-ids", str(person_id)],
    )
    weight_args = parser.parse_args(
        ["persons", "weights", "--person-ids", str(person_id)],
    )

    assert assessment_args.command == "persons"
    assert assessment_args.persons_command == "assessments"
    assert assessment_args.person_ids == [person_id]
    assert weight_args.persons_command == "weights"
    assert weight_args.person_ids == [person_id]


def test_person_assessments_command_queries_requested_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    person_id = 42
    assessment = PersonAssessment(
        person_id=person_id,
        content="Assessment",
        content_hash="hash",
        assessment_date=datetime(2026, 8, 28, tzinfo=UTC).date(),
        created_by="model",
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        def get_assessments_by_person_ids(
            person_ids: list[int],
        ) -> list[PersonAssessment]:
            assert person_ids == [person_id]
            return [assessment]

    monkeypatch.setattr(assessments, "PersonRepo", Repository)

    output = PersonAssessmentsController(
        session="session",  # ty: ignore[invalid-argument-type]
    ).run(PersonAssessmentsOptions(person_ids=[person_id]))

    assert output.result.assessments == [assessment]
    assert '"content": "Assessment"' in output.result.to_console()


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
