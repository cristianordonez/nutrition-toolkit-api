from __future__ import annotations

import asyncio
import typing
from datetime import date

from ntk.controllers.assessment import generate
from ntk.controllers.assessment.generate import (
    AssessmentGenerationController,
    AssessmentGenerationOptions,
    PersonAssessmentGenerationOptions,
)
from ntk.models.sql.person import Person, PersonAssessment

if typing.TYPE_CHECKING:
    import pytest


def test_generation_controller_passes_context_for_each_person(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_person = Person(id=1, name="Person")
    second_person = Person(id=2, name="Second Person")

    class PersonRepository:
        def __init__(self, _session: object) -> None:
            pass

    class Service:
        def __init__(self, *_repositories: object, **_dependencies: object) -> None:
            pass

        generated: typing.ClassVar[list[tuple[str, str | None, str | None]]] = []

        @classmethod
        async def generate_many(
            cls,
            requests: list[PersonAssessmentGenerationOptions],
        ) -> list[PersonAssessment]:
            seen: set[tuple[str | None, str]] = set()
            results: list[PersonAssessment] = []
            for request in requests:
                key = (request.facility_identifier, request.source_person_identifier)
                if key in seen:
                    continue
                seen.add(key)
                cls.generated.append(
                    (
                        request.source_person_identifier,
                        request.facility_identifier,
                        request.context,
                    ),
                )
                value = (
                    first_person
                    if request.source_person_identifier == "R-1"
                    else second_person
                )
                results.append(
                    PersonAssessment(
                        person_id=typing.cast("int", value.id),
                        person=value,
                        content="Assessment",
                        content_hash="hash",
                        assessment_date=date(2026, 8, 30),
                        created_by="model",
                    ),
                )
            return results

    monkeypatch.setattr(generate, "PersonRepo", PersonRepository)
    monkeypatch.setattr(generate, "AssessmentPipeline", Service)

    output = asyncio.run(
        AssessmentGenerationController(session=object()).run(  # ty: ignore[invalid-argument-type]
            AssessmentGenerationOptions(
                persons=[
                    PersonAssessmentGenerationOptions(
                        source_person_identifier="R-1",
                        facility_identifier="FAC-1",
                        context="wound healing",
                    ),
                    PersonAssessmentGenerationOptions(
                        source_person_identifier="R-2",
                        facility_identifier="FAC-1",
                        context="renal nutrition",
                    ),
                    PersonAssessmentGenerationOptions(
                        source_person_identifier="R-1",
                        facility_identifier="FAC-1",
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
    assert [result.person_name for result in output.result.assessments] == [
        "Person",
        "Second Person",
    ]
