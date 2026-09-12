from __future__ import annotations

import asyncio
import typing
from datetime import date

import pytest

from ntk.models.person_detail import (
    AnthropometricCalculations,
    DerivedPersonCalculations,
    NutritionNeedsCalculation,
    ParenteralNutritionCalculation,
    PersonDetail,
    TubeFeedCalculation,
)
from ntk.models.rag import RagSearchMatch
from ntk.models.sql.person import Person, PersonAssessment
from ntk.pipelines.assessment.create import pipeline as generation_pipeline

if typing.TYPE_CHECKING:
    from ntk.models.assessment_context import BudgetedAssessmentContext


def _detail() -> PersonDetail:
    return PersonDetail(
        person_id=7,
        name="Doe, Jane",
        first_name="Jane",
        last_name="Doe",
        derived_calculations=DerivedPersonCalculations(
            calculated_on=date(2026, 9, 7),
            anthropometrics=AnthropometricCalculations(),
            nutrition_needs=NutritionNeedsCalculation(status="not_computed"),
            tube_feed=TubeFeedCalculation(status="not_applicable"),
            parenteral_nutrition=ParenteralNutritionCalculation(
                status="not_applicable",
            ),
        ),
    )


def test_generate_for_person_prepares_and_passes_budgeted_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    person = Person(id=7, name="Doe, Jane")
    detail = _detail()
    captured: list[BudgetedAssessmentContext] = []

    class Agent:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs == {
                "food_repo": food_repository,
                "embedding_service": embedding_service,
            }

        @staticmethod
        async def run(context: BudgetedAssessmentContext) -> str:
            captured.append(context)
            return "Generated assessment"

    class Embeddings:
        @staticmethod
        def search_assessments(text: str, *, top_k: int) -> list[RagSearchMatch]:
            assert text == detail.create_summary_text()
            assert top_k == 5  # noqa: PLR2004
            return [
                RagSearchMatch(
                    document_id=12,
                    filename="similar-assessment.txt",
                    chunk_text="Similar assessment style",
                    similarity=0.91,
                ),
            ]

    class Repository:
        @staticmethod
        def create(assessment: PersonAssessment) -> PersonAssessment:
            assessment.id = 31
            return assessment

    monkeypatch.setattr(generation_pipeline, "AssessmentAgent", Agent)
    food_repository = object()
    embedding_service = Embeddings()
    pipeline = generation_pipeline.AssessmentPipeline(
        Repository(),  # ty: ignore[invalid-argument-type]
        food_repository=food_repository,  # ty: ignore[invalid-argument-type]
        embedding_service=embedding_service,  # ty: ignore[invalid-argument-type]
    )

    result = asyncio.run(
        pipeline.generate_for_person(
            person,
            detail,
            context="wound review",
        ),
    )

    assert len(captured) == 1
    assert captured[0].person.name == detail.name
    assert captured[0].relevant_assessments[0].document_id == 12  # noqa: PLR2004
    assert captured[0].additional_context == "wound review"
    assert result.id == 31  # noqa: PLR2004
    assert result.person_id == 7  # noqa: PLR2004
    assert result.content == "Generated assessment"


def test_prepare_context_propagates_retrieval_failure() -> None:
    class Embeddings:
        @staticmethod
        def search_assessments(_text: str, *, top_k: int) -> list[RagSearchMatch]:
            assert top_k == 5  # noqa: PLR2004
            msg = "vector index unavailable"
            raise RuntimeError(msg)

    pipeline = generation_pipeline.AssessmentPipeline(
        object(),  # ty: ignore[invalid-argument-type]
        embedding_service=Embeddings(),  # ty: ignore[invalid-argument-type]
    )

    with pytest.raises(RuntimeError, match="vector index unavailable"):
        asyncio.run(pipeline.prepare_context(_detail()))


def test_generate_for_person_rejects_mismatched_detail() -> None:
    pipeline = generation_pipeline.AssessmentPipeline(
        object(),  # ty: ignore[invalid-argument-type]
    )

    with pytest.raises(ValueError, match="does not belong"):
        asyncio.run(
            pipeline.generate_for_person(
                Person(id=8, name="Other, Person"),
                _detail(),
            ),
        )
