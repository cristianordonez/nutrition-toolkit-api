from __future__ import annotations

import argparse
import asyncio
import typing
from datetime import UTC, datetime

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
from engine.models.sql.person import PersonWeight
from ntk.models.ncp_public import NutritionCareProcessPublic

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


def test_person_ncps_command_queries_cloud_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ncp = NutritionCareProcessPublic(
        id=1,
        person_identifier="person-42",
        note_text="Assessment",
        content_hash="hash",
        created_by="model",
        status="draft",
        created_at=datetime(2026, 8, 28, tzinfo=UTC),
    )

    class Client:
        async def list_ncps(
            self,
            person_identifier: str,
        ) -> list[NutritionCareProcessPublic]:
            assert person_identifier == "person-42"
            return [ncp]

    output = asyncio.run(
        PersonNCPsController(client=Client()).run(  # ty: ignore[invalid-argument-type]
            PersonNCPsOptions(person_identifier="person-42"),
        ),
    )

    assert output.result.ncps == [ncp]
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
