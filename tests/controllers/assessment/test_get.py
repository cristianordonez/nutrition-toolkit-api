from __future__ import annotations

from datetime import date

import pytest

from ntk.controllers.assessment import get
from ntk.controllers.assessment.get import (
    AssessmentGetCommandController,
    AssessmentGetOptions,
)
from ntk.models.sql.resident import ResidentAssessment


def test_get_controller_returns_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = ResidentAssessment(
        id=1,
        resident_id=1,
        content="Assessment",
        content_hash="hash",
        assessment_date=date(2026, 8, 31),
        created_by="model",
    )

    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        @staticmethod
        def get_by_id(assessment_id: int) -> ResidentAssessment | None:
            return assessment if assessment_id == assessment.id else None

    monkeypatch.setattr(get, "AssessmentRepo", Repository)

    output = AssessmentGetCommandController(session=object()).run(  # ty: ignore[invalid-argument-type]
        AssessmentGetOptions(assessment_id=1),
    )

    assert output.result.assessment is assessment


def test_get_controller_rejects_unknown_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        @staticmethod
        def get_by_id(_assessment_id: int) -> None:
            return None

    monkeypatch.setattr(get, "AssessmentRepo", Repository)

    with pytest.raises(LookupError, match="was not found"):
        AssessmentGetCommandController(session=object()).run(  # ty: ignore[invalid-argument-type]
            AssessmentGetOptions(assessment_id=999),
        )
