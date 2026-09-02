from __future__ import annotations

import asyncio
from datetime import date

import pytest

from ntk.controllers.assessment import finalize
from ntk.controllers.assessment.finalize import (
    AssessmentFinalizeController,
    AssessmentFinalizeOptions,
)
from ntk.models.sql.resident import ResidentAssessment, StatusType


def test_finalize_controller_returns_updated_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = ResidentAssessment(
        id=1,
        resident_id=1,
        content="Assessment",
        content_hash="hash",
        assessment_date=date(2026, 8, 31),
        created_by="model",
        status=StatusType.FINALIZED,
    )

    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        @staticmethod
        def finalize(assessment_id: int) -> ResidentAssessment | None:
            return assessment if assessment_id == assessment.id else None

        @staticmethod
        def get_embedding(_assessment_id: int) -> object:
            return object()

    monkeypatch.setattr(finalize, "AssessmentRepo", Repository)

    output = asyncio.run(
        AssessmentFinalizeController(
            session=object(),  # ty: ignore[invalid-argument-type]
        ).run(AssessmentFinalizeOptions(assessment_id=1)),
    )

    assert output.result is assessment


def test_finalize_controller_rejects_unknown_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        @staticmethod
        def finalize(_assessment_id: int) -> None:
            return None

    monkeypatch.setattr(finalize, "AssessmentRepo", Repository)

    with pytest.raises(LookupError, match="was not found"):
        asyncio.run(
            AssessmentFinalizeController(
                session=object(),  # ty: ignore[invalid-argument-type]
            ).run(AssessmentFinalizeOptions(assessment_id=999)),
        )
