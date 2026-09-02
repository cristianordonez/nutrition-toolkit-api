from __future__ import annotations

import argparse
import typing
from datetime import UTC, datetime

from ntk.controllers.residents import assessments, weights
from ntk.controllers.residents.app import ResidentControllerGroup
from ntk.controllers.residents.assessments import (
    ResidentAssessmentsController,
    ResidentAssessmentsOptions,
)
from ntk.controllers.residents.weights import (
    ResidentWeightsController,
    ResidentWeightsOptions,
)
from ntk.models.sql.resident import ResidentAssessment, ResidentWeight

if typing.TYPE_CHECKING:
    import pytest


def test_resident_group_registers_plural_query_commands() -> None:
    resident_id = 42
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    ResidentControllerGroup().register(subparsers)

    assessment_args = parser.parse_args(
        ["residents", "assessments", "--resident-ids", str(resident_id)],
    )
    weight_args = parser.parse_args(
        ["residents", "weights", "--resident-ids", str(resident_id)],
    )

    assert assessment_args.command == "residents"
    assert assessment_args.residents_command == "assessments"
    assert assessment_args.resident_ids == [resident_id]
    assert weight_args.residents_command == "weights"
    assert weight_args.resident_ids == [resident_id]


def test_resident_assessments_command_queries_requested_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resident_id = 42
    assessment = ResidentAssessment(
        resident_id=resident_id,
        content="Assessment",
        content_hash="hash",
        assessment_date=datetime(2026, 8, 28, tzinfo=UTC).date(),
        created_by="model",
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        def get_assessments_by_resident_ids(
            resident_ids: list[int],
        ) -> list[ResidentAssessment]:
            assert resident_ids == [resident_id]
            return [assessment]

    monkeypatch.setattr(assessments, "ResidentRepo", Repository)

    output = ResidentAssessmentsController(
        session="session",  # ty: ignore[invalid-argument-type]
    ).run(ResidentAssessmentsOptions(resident_ids=[resident_id]))

    assert output.result.assessments == [assessment]
    assert '"content": "Assessment"' in output.result.to_console()


def test_resident_weights_command_queries_requested_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resident_id = 42
    weight = ResidentWeight(
        resident_id=resident_id,
        measured_at=datetime(2026, 8, 28, tzinfo=UTC),
        weight_lb=150,
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        def get_weights_by_resident_ids(
            resident_ids: list[int],
        ) -> list[ResidentWeight]:
            assert resident_ids == [resident_id]
            return [weight]

    monkeypatch.setattr(weights, "ResidentRepo", Repository)

    output = ResidentWeightsController(
        session="session",  # ty: ignore[invalid-argument-type]
    ).run(ResidentWeightsOptions(resident_ids=[resident_id]))

    assert output.result.weights == [weight]
    assert '"weight_lb": 150.0' in output.result.to_console()
