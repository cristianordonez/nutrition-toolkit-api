from __future__ import annotations

from datetime import date

import pytest

from ntk.controllers.ncp import get
from ntk.controllers.ncp.get import (
    NCPGetCommandController,
    NCPGetOptions,
)
from ntk.models.sql.person import PersonClinicalNote


def test_get_controller_returns_assessment(
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
    )

    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        @staticmethod
        def get_ncp(ncp_id: int) -> PersonClinicalNote | None:
            return assessment if ncp_id == assessment.id else None

    monkeypatch.setattr(get, "ClinicalNoteRepo", Repository)

    output = NCPGetCommandController(session=object()).run(  # ty: ignore[invalid-argument-type]
        NCPGetOptions(ncp_id=1),
    )

    assert output.result.ncp is assessment


def test_get_controller_rejects_unknown_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        @staticmethod
        def get_ncp(_ncp_id: int) -> None:
            return None

    monkeypatch.setattr(get, "ClinicalNoteRepo", Repository)

    with pytest.raises(LookupError, match="was not found"):
        NCPGetCommandController(session=object()).run(  # ty: ignore[invalid-argument-type]
            NCPGetOptions(ncp_id=999),
        )
