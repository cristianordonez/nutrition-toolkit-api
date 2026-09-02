from __future__ import annotations

import asyncio
import typing
from datetime import date

from ntk.models.sql.resident import ResidentAssessment
from ntk.services.assessment import AssessmentFinalizationService


def test_finalization_service_delegates_to_repository() -> None:
    assessment = ResidentAssessment(
        id=1,
        resident_id=1,
        content="Nutrition assessment",
        content_hash="hash",
        assessment_date=date(2026, 8, 30),
        created_by="model",
    )

    class Repository:
        @staticmethod
        def finalize(assessment_id: object) -> ResidentAssessment | None:
            return assessment if assessment_id == assessment.id else None

    class EmbeddingService:
        embedded: typing.ClassVar[list[ResidentAssessment]] = []

        @classmethod
        async def embed_assessment(cls, value: ResidentAssessment) -> bool:
            cls.embedded.append(value)
            return True

    result = asyncio.run(
        AssessmentFinalizationService(
            Repository(),  # ty: ignore[invalid-argument-type]
            EmbeddingService(),  # ty: ignore[invalid-argument-type]
        ).finalize(1),
    )

    assert result is assessment
    assert EmbeddingService.embedded == [assessment]
