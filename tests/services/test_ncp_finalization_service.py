from __future__ import annotations

import asyncio
import typing
from datetime import UTC, datetime

from ntk.models.sql.person import (
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
    NutritionClinicalNoteType,
    PersonClinicalNote,
)
from ntk.pipelines.ncp import NutritionCareProcessPipeline


def test_finalization_service_delegates_to_repository() -> None:
    assessment = PersonClinicalNote(
        id=1,
        person_id=1,
        note_date=datetime(2026, 8, 30, tzinfo=UTC),
        note_type="Nutrition/Dietary",
        note_text="Nutrition assessment",
        raw_text="Nutrition assessment",
        note_key="ncp-1",
        ncp_source=NutritionCareProcessSource.GENERATED,
        content_hash="hash",
        ncp_index=0,
        created_by="model",
        status=NutritionCareProcessStatus.DRAFT,
    )

    class Repository:
        updated: typing.ClassVar[list[PersonClinicalNote]] = []

        @staticmethod
        def finalize_ncp(ncp_id: object) -> PersonClinicalNote | None:
            assessment.status = NutritionCareProcessStatus.FINALIZED
            return assessment if ncp_id == assessment.id else None

        @staticmethod
        def get_embedding(_ncp_id: int) -> None:
            return None

        @classmethod
        def update_ncp(
            cls,
            value: PersonClinicalNote,
            *,
            embedding: list[float],
            embedding_type: NutritionClinicalNoteType,
            model_name: str,
        ) -> PersonClinicalNote:
            assert embedding == [0.1]
            assert embedding_type is NutritionClinicalNoteType.NUTRITION_DIETARY
            assert model_name == "embedding-model"
            cls.updated.append(value)
            return value

    class EmbeddingService:
        embedding_model = "embedding-model"

        @staticmethod
        async def get_embedding_async(content: str) -> list[float]:
            assert content == assessment.note_text
            return [0.1]

    result = asyncio.run(
        NutritionCareProcessPipeline(
            Repository(),  # ty: ignore[invalid-argument-type]
            embedding_service=EmbeddingService(),  # ty: ignore[invalid-argument-type]
        ).finalize(1),
    )

    assert result is assessment
    assert Repository.updated == [assessment]
