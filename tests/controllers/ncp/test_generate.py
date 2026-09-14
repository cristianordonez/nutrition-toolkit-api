from __future__ import annotations

import asyncio
import typing
from datetime import UTC, datetime

from ntk.controllers.ncp import generate
from ntk.controllers.ncp.generate import (
    NCPGenerationController,
    NCPGenerationOptions,
    PersonNCPGenerationOptions,
)
from ntk.models.sql.person import (
    ExtractionStatus,
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
    Person,
    PersonClinicalNote,
)

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
            requests: list[PersonNCPGenerationOptions],
        ) -> list[PersonClinicalNote]:
            seen: set[tuple[str | None, str]] = set()
            results: list[PersonClinicalNote] = []
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
                    PersonClinicalNote(
                        person_id=typing.cast("int", value.id),
                        person=value,
                        note_date=datetime(2026, 8, 30, tzinfo=UTC),
                        note_type="Nutrition/Dietary",
                        author="model",
                        note_text="Assessment",
                        raw_text="Assessment",
                        note_key=f"generated-{value.id}",
                        extraction_status=ExtractionStatus.NOT_APPLICABLE,
                        ncp_source=NutritionCareProcessSource.GENERATED,
                        content_hash="hash",
                        ncp_index=0,
                        created_by="model",
                        status=NutritionCareProcessStatus.DRAFT,
                    ),
                )
            return results

    monkeypatch.setattr(generate, "PersonRepo", PersonRepository)
    monkeypatch.setattr(generate, "NutritionCareProcessPipeline", Service)

    output = asyncio.run(
        NCPGenerationController(session=object()).run(  # ty: ignore[invalid-argument-type]
            NCPGenerationOptions(
                persons=[
                    PersonNCPGenerationOptions(
                        source_person_identifier="R-1",
                        facility_identifier="FAC-1",
                        context="wound healing",
                    ),
                    PersonNCPGenerationOptions(
                        source_person_identifier="R-2",
                        facility_identifier="FAC-1",
                        context="renal nutrition",
                    ),
                    PersonNCPGenerationOptions(
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
    assert len(output.result.ncps) == len(expected)
    assert [result.person_name for result in output.result.ncps] == [
        "Person",
        "Second Person",
    ]
