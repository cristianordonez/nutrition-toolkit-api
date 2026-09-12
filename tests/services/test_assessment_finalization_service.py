from __future__ import annotations

import asyncio
import typing
from datetime import date

from ntk.models.sql.person import PersonAssessment, StatusType
from ntk.pipelines.assessment import AssessmentPipeline


def test_finalization_service_delegates_to_repository() -> None:
    assessment = PersonAssessment(
        id=1,
        person_id=1,
        content="Nutrition assessment",
        content_hash="hash",
        assessment_date=date(2026, 8, 30),
        created_by="model",
    )

    class Repository:
        updated: typing.ClassVar[list[PersonAssessment]] = []

        @staticmethod
        def finalize(assessment_id: object) -> PersonAssessment | None:
            assessment.status = StatusType.FINALIZED
            return assessment if assessment_id == assessment.id else None

        @staticmethod
        def get_embedding(_assessment_id: int) -> None:
            return None

        @classmethod
        def update(
            cls,
            value: PersonAssessment,
            *,
            embedding: list[float],
            model_name: str,
        ) -> PersonAssessment:
            assert embedding == [0.1]
            assert model_name == "embedding-model"
            cls.updated.append(value)
            return value

    class EmbeddingService:
        embedding_model = "embedding-model"

        @staticmethod
        async def get_embedding_async(content: str) -> list[float]:
            assert content == assessment.content
            return [0.1]

    result = asyncio.run(
        AssessmentPipeline(
            Repository(),  # ty: ignore[invalid-argument-type]
            embedding_service=EmbeddingService(),  # ty: ignore[invalid-argument-type]
        ).finalize(1),
    )

    assert result is assessment
    assert Repository.updated == [assessment]
