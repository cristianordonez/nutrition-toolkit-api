from __future__ import annotations

import asyncio
import typing
from datetime import date

from ntk.controllers.assessment import generate as generate_command
from ntk.controllers.assessment.generate import (
    AssessmentGenerateCommandController,
    AssessmentGenerateCommandOptions,
)
from ntk.models.sql.resident import Resident, ResidentAssessment

if typing.TYPE_CHECKING:
    import pytest


def test_generate_command_calls_generation_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resident_id = 1
    resident_identifier = "R-1"
    resident = Resident(
        id=resident_id,
        name="Resident",
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Service:
        def __init__(self, *_repositories: object) -> None:
            pass

        @staticmethod
        async def generate(
            value: str,
            *,
            facility_id: str | None = None,
            context: str | None = None,
        ) -> ResidentAssessment:
            assert value == resident_identifier
            assert facility_id == "FAC"
            assert context == "wound healing"
            return ResidentAssessment(
                resident_id=typing.cast("int", resident.id),
                content="Assessment",
                content_hash="hash",
                assessment_date=date(2026, 8, 30),
                created_by="model",
            )

    monkeypatch.setattr(generate_command, "AssessmentRepo", Repository)
    monkeypatch.setattr(generate_command, "EmbeddingRepo", Repository)
    monkeypatch.setattr(generate_command, "ResidentRepo", Repository)
    monkeypatch.setattr(generate_command, "AssessmentGenerationService", Service)

    output = asyncio.run(
        AssessmentGenerateCommandController(
            session="session",  # ty: ignore[invalid-argument-type]
        ).run(
            AssessmentGenerateCommandOptions(
                resident_identifiers=[resident_identifier],
                facility_id="FAC",
                context="wound healing",
            ),
        ),
    )

    assert len(output.result.assessments) == 1
