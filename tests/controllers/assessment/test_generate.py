from __future__ import annotations

import asyncio
import typing
from datetime import date

from ntk.controllers.assessment import generation as generate
from ntk.controllers.assessment.generation import (
    AssessmentGenerationController,
    AssessmentGenerationOptions,
    ResidentAssessmentGenerationOptions,
)
from ntk.models.sql.resident import Resident, ResidentAssessment

if typing.TYPE_CHECKING:
    import pytest


def test_generation_controller_passes_context_for_each_resident(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_resident = Resident(id=1, name="Resident")
    second_resident = Resident(id=2, name="Second Resident")

    class ResidentRepository:
        def __init__(self, _session: object) -> None:
            pass

    class Service:
        def __init__(self, *_repositories: object) -> None:
            pass

        generated: typing.ClassVar[list[tuple[str, str | None, str | None]]] = []

        @classmethod
        async def generate(
            cls,
            resident_identifier: str,
            *,
            facility_id: str | None = None,
            context: str | None = None,
        ) -> ResidentAssessment:
            cls.generated.append((resident_identifier, facility_id, context))
            value = first_resident if resident_identifier == "R-1" else second_resident
            return ResidentAssessment(
                resident_id=typing.cast("int", value.id),
                resident=value,
                content="Assessment",
                content_hash="hash",
                assessment_date=date(2026, 8, 30),
                created_by="model",
            )

    monkeypatch.setattr(generate, "ResidentRepo", ResidentRepository)
    monkeypatch.setattr(generate, "AssessmentGenerationService", Service)

    output = asyncio.run(
        AssessmentGenerationController(session=object()).run(  # ty: ignore[invalid-argument-type]
            AssessmentGenerationOptions(
                residents=[
                    ResidentAssessmentGenerationOptions(
                        resident_identifier="R-1",
                        facility_id="FAC-1",
                        context="wound healing",
                    ),
                    ResidentAssessmentGenerationOptions(
                        resident_identifier="R-2",
                        facility_id="FAC-1",
                        context="renal nutrition",
                    ),
                    ResidentAssessmentGenerationOptions(
                        resident_identifier="R-1",
                        facility_id="FAC-1",
                        context="duplicate request",
                    ),
                ],
            ),
        ),
    )

    expected = [
        ("R-1", "FAC-1", "wound healing"),
        ("R-2", "FAC-1", "renal nutrition"),
    ]
    assert Service.generated == expected
    assert len(output.result.assessments) == len(expected)
    assert [result.resident_name for result in output.result.assessments] == [
        "Resident",
        "Second Resident",
    ]
