from __future__ import annotations

import asyncio
from datetime import date
from hashlib import sha256

import pytest

from ntk.models.sql.resident import ResidentAssessment, StatusType
from ntk.services.assessment import update_service
from ntk.services.assessment.update_service import AssessmentUpdateService


class Repository:
    def __init__(self, assessment: ResidentAssessment | None) -> None:
        self.assessment = assessment
        self.updated: list[
            tuple[ResidentAssessment, list[float] | None, str | None]
        ] = []

    def get_by_id(self, _assessment_id: int) -> ResidentAssessment | None:
        return self.assessment

    def update(
        self,
        assessment: ResidentAssessment,
        *,
        embedding: list[float] | None,
        model_name: str | None,
    ) -> ResidentAssessment:
        self.updated.append((assessment, embedding, model_name))
        return assessment


def _assessment() -> ResidentAssessment:
    return ResidentAssessment(
        id=1,
        resident_id=1,
        content="Original",
        content_hash="old-hash",
        assessment_date=date(2026, 8, 1),
        created_by="model",
    )


def test_update_changes_fields_and_refreshes_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = _assessment()
    repository = Repository(assessment)

    class Embeddings:
        embedding_model = "embedding-model"

        @staticmethod
        async def get_embedding_async(text: str) -> list[float]:
            assert text == "Updated   assessment"
            return [0.1, 0.2]

    monkeypatch.setattr(update_service, "EmbeddingService", Embeddings)

    result = asyncio.run(
        AssessmentUpdateService(repository).update(  # ty: ignore[invalid-argument-type]
            1,
            content="  Updated   assessment  ",
            assessment_date=date(2026, 8, 31),
            created_by="  dietitian  ",
            status=StatusType.FINALIZED,
        ),
    )

    assert result is assessment
    assert assessment.content == "Updated   assessment"
    assert assessment.content_hash == sha256(b"Updated assessment").hexdigest()
    assert assessment.assessment_date == date(2026, 8, 31)
    assert assessment.created_by == "dietitian"
    assert assessment.status is StatusType.FINALIZED
    assert assessment.finalized_at is not None
    assert repository.updated == [(assessment, [0.1, 0.2], "embedding-model")]


def test_update_handles_missing_draft_and_invalid_values() -> None:
    missing = AssessmentUpdateService(Repository(None)).update(  # ty: ignore[invalid-argument-type]
        999,
    )
    assert asyncio.run(missing) is None

    assessment = _assessment()
    assessment.status = StatusType.FINALIZED
    repository = Repository(assessment)
    result = asyncio.run(
        AssessmentUpdateService(repository).update(  # ty: ignore[invalid-argument-type]
            1,
            status=StatusType.DRAFT,
        ),
    )
    assert result is assessment
    assert assessment.finalized_at is None

    with pytest.raises(ValueError, match="content cannot be empty"):
        asyncio.run(
            AssessmentUpdateService(repository).update(  # ty: ignore[invalid-argument-type]
                1,
                content="  ",
            ),
        )
    with pytest.raises(ValueError, match="creator cannot be empty"):
        asyncio.run(
            AssessmentUpdateService(repository).update(  # ty: ignore[invalid-argument-type]
                1,
                created_by="  ",
            ),
        )


def test_updating_draft_content_does_not_create_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = _assessment()
    repository = Repository(assessment)

    class Embeddings:
        def __init__(self) -> None:
            msg = "Draft content must not be embedded"
            raise AssertionError(msg)

    monkeypatch.setattr(update_service, "EmbeddingService", Embeddings)

    result = asyncio.run(
        AssessmentUpdateService(repository).update(  # ty: ignore[invalid-argument-type]
            1,
            content="Updated draft",
        ),
    )

    assert result is assessment
    assert assessment.status is StatusType.DRAFT
    assert repository.updated == [(assessment, None, None)]
