from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from hashlib import sha256

import pytest

from ntk.models.sql.person import (
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
    NutritionClinicalNoteType,
    PersonClinicalNote,
)
from ntk.pipelines.ncp import FinalizedNCPError, NutritionCareProcessPipeline


class Repository:
    def __init__(self, assessment: PersonClinicalNote | None) -> None:
        self.assessment = assessment
        self.updated: list[
            tuple[
                PersonClinicalNote,
                list[float] | None,
                NutritionClinicalNoteType | None,
                str | None,
            ]
        ] = []

    def get_ncp(self, _ncp_id: int) -> PersonClinicalNote | None:
        return self.assessment

    def update_ncp(
        self,
        assessment: PersonClinicalNote,
        *,
        embedding: list[float] | None,
        embedding_type: NutritionClinicalNoteType | None,
        model_name: str | None,
    ) -> PersonClinicalNote:
        self.updated.append((assessment, embedding, embedding_type, model_name))
        return assessment


def _assessment() -> PersonClinicalNote:
    return PersonClinicalNote(
        id=1,
        person_id=1,
        note_date=datetime(2026, 8, 1, tzinfo=UTC),
        note_type="Nutrition/Dietary",
        note_text="Original",
        raw_text="Original",
        note_key="ncp-1",
        ncp_source=NutritionCareProcessSource.GENERATED,
        content_hash="old-hash",
        ncp_index=0,
        created_by="model",
        status=NutritionCareProcessStatus.DRAFT,
    )


def test_update_changes_fields_and_refreshes_embedding() -> None:
    assessment = _assessment()
    repository = Repository(assessment)

    class Embeddings:
        embedding_model = "embedding-model"

        @staticmethod
        async def get_embedding_async(text: str) -> list[float]:
            assert text == "Updated   assessment"
            return [0.1, 0.2]

    result = asyncio.run(
        NutritionCareProcessPipeline(
            repository,  # ty: ignore[invalid-argument-type]
            embedding_service=Embeddings(),  # ty: ignore[invalid-argument-type]
        ).update(
            1,
            note_text="  Updated   assessment  ",
            note_date=datetime(2026, 8, 31, tzinfo=UTC),
            created_by="  dietitian  ",
            status=NutritionCareProcessStatus.FINALIZED,
        ),
    )

    assert result is assessment
    assert assessment.note_text == "Updated   assessment"
    assert assessment.content_hash == sha256(b"Updated assessment").hexdigest()
    assert assessment.note_date == datetime(2026, 8, 31, tzinfo=UTC)
    assert assessment.created_by == "dietitian"
    assert assessment.status is NutritionCareProcessStatus.FINALIZED
    assert assessment.finalized_at is not None
    assert repository.updated == [
        (
            assessment,
            [0.1, 0.2],
            NutritionClinicalNoteType.NUTRITION_DIETARY,
            "embedding-model",
        ),
    ]


def test_update_handles_missing_draft_and_invalid_values() -> None:
    missing = NutritionCareProcessPipeline(Repository(None)).update(  # ty: ignore[invalid-argument-type]
        999,
    )
    assert asyncio.run(missing) is None

    assessment = _assessment()
    repository = Repository(assessment)

    with pytest.raises(ValueError, match="content cannot be empty"):
        asyncio.run(
            NutritionCareProcessPipeline(repository).update(  # ty: ignore[invalid-argument-type]
                1,
                note_text="  ",
            ),
        )
    with pytest.raises(ValueError, match="creator cannot be empty"):
        asyncio.run(
            NutritionCareProcessPipeline(repository).update(  # ty: ignore[invalid-argument-type]
                1,
                created_by="  ",
            ),
        )


def test_editing_finalized_ncp_fails_without_mutating_it() -> None:
    assessment = _assessment()
    assessment.status = NutritionCareProcessStatus.FINALIZED
    original_content = assessment.note_text
    original_hash = assessment.content_hash
    repository = Repository(assessment)

    with pytest.raises(FinalizedNCPError, match="finalized and cannot be edited"):
        asyncio.run(
            NutritionCareProcessPipeline(repository).update(  # ty: ignore[invalid-argument-type]
                1,
                note_text="Replacement content",
            ),
        )

    assert assessment.note_text == original_content
    assert assessment.content_hash == original_hash
    assert assessment.status is NutritionCareProcessStatus.FINALIZED
    assert repository.updated == []


def test_finalized_ncp_cannot_transition_back_to_draft() -> None:
    assessment = _assessment()
    assessment.status = NutritionCareProcessStatus.FINALIZED
    repository = Repository(assessment)

    with pytest.raises(FinalizedNCPError, match="finalized and cannot be edited"):
        asyncio.run(
            NutritionCareProcessPipeline(repository).update(  # ty: ignore[invalid-argument-type]
                1,
                status=NutritionCareProcessStatus.DRAFT,
            ),
        )

    assert assessment.status is NutritionCareProcessStatus.FINALIZED
    assert repository.updated == []


def test_updating_draft_content_does_not_create_embedding() -> None:
    assessment = _assessment()
    repository = Repository(assessment)

    result = asyncio.run(
        NutritionCareProcessPipeline(repository).update(  # ty: ignore[invalid-argument-type]
            1,
            note_text="Updated draft",
        ),
    )

    assert result is assessment
    assert assessment.status is NutritionCareProcessStatus.DRAFT
    assert repository.updated == [(assessment, None, None, None)]
