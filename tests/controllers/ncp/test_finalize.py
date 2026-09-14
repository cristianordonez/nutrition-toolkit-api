from __future__ import annotations

import asyncio
from datetime import date

import pytest

from ntk.controllers.ncp import finalize
from ntk.controllers.ncp.finalize import (
    NCPFinalizeController,
    NCPFinalizeOptions,
)
from ntk.models.sql.person import NutritionCareProcessStatus, PersonClinicalNote


def test_finalize_controller_returns_updated_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = PersonClinicalNote(
        id=1,
        person_id=1,
        note_text="Assessment",
        raw_text="Assessment",
        note_key="ncp-1",
        content_hash="hash",
        note_date=date(2026, 8, 31),
        created_by="model",
        status=NutritionCareProcessStatus.FINALIZED,
    )

    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        @staticmethod
        def finalize_ncp(ncp_id: int) -> PersonClinicalNote | None:
            return assessment if ncp_id == assessment.id else None

        @staticmethod
        def get_embedding(_ncp_id: int) -> object:
            return object()

    monkeypatch.setattr(finalize, "ClinicalNoteRepo", Repository)

    output = asyncio.run(
        NCPFinalizeController(
            session=object(),  # ty: ignore[invalid-argument-type]
        ).run(NCPFinalizeOptions(ncp_id=1)),
    )

    assert output.result is assessment


def test_finalize_controller_rejects_unknown_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        @staticmethod
        def finalize_ncp(_ncp_id: int) -> None:
            return None

    monkeypatch.setattr(finalize, "ClinicalNoteRepo", Repository)

    with pytest.raises(LookupError, match="was not found"):
        asyncio.run(
            NCPFinalizeController(
                session=object(),  # ty: ignore[invalid-argument-type]
            ).run(NCPFinalizeOptions(ncp_id=999)),
        )
