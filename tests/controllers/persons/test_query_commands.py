from __future__ import annotations

import argparse
import typing
from datetime import UTC, datetime

from ntk.controllers.persons import ncps, weights
from ntk.controllers.persons.app import PersonControllerGroup
from ntk.controllers.persons.ncps import (
    PersonNCPsController,
    PersonNCPsOptions,
)
from ntk.controllers.persons.weights import (
    PersonWeightsController,
    PersonWeightsOptions,
)
from ntk.models.sql.person import (
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
    PersonClinicalNote,
    PersonWeight,
)

if typing.TYPE_CHECKING:
    import pytest


def test_person_group_registers_plural_query_commands() -> None:
    person_id = 42
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    PersonControllerGroup().register(subparsers)

    assessment_args = parser.parse_args(
        ["persons", "ncps", "--person-ids", str(person_id)],
    )
    weight_args = parser.parse_args(
        ["persons", "weights", "--person-ids", str(person_id)],
    )

    assert assessment_args.command == "persons"
    assert assessment_args.persons_command == "ncps"
    assert assessment_args.person_ids == [person_id]
    assert weight_args.persons_command == "weights"
    assert weight_args.person_ids == [person_id]


def test_person_ncps_command_queries_requested_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    person_id = 42
    assessment = PersonClinicalNote(
        person_id=person_id,
        note_date=datetime(2026, 8, 28, tzinfo=UTC),
        note_type="Nutrition/Dietary",
        note_text="Assessment",
        raw_text="Assessment",
        note_key="ncp-42",
        ncp_source=NutritionCareProcessSource.GENERATED,
        content_hash="hash",
        ncp_index=0,
        created_by="model",
        status=NutritionCareProcessStatus.DRAFT,
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        def get_ncps_by_person_ids(
            person_ids: list[int],
        ) -> list[PersonClinicalNote]:
            assert person_ids == [person_id]
            return [assessment]

    monkeypatch.setattr(ncps, "PersonRepo", Repository)

    output = PersonNCPsController(
        session="session",  # ty: ignore[invalid-argument-type]
    ).run(PersonNCPsOptions(person_ids=[person_id]))

    assert output.result.ncps == [assessment]
    assert '"note_text": "Assessment"' in output.result.to_console()


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
