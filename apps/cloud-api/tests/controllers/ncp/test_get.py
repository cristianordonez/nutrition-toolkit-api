from __future__ import annotations

from datetime import UTC, datetime

import pytest

from api.controllers.ncp import get
from api.controllers.ncp.get import (
    NCPGetCommandController,
    NCPGetOptions,
)
from api.models.sql.ncp import NutritionCareProcess


def test_get_controller_returns_ncp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ncp = NutritionCareProcess(
        id=1,
        person_identifier="person-1",
        note_text="Assessment",
        content_hash="hash",
        created_by="model",
        created_at=datetime(2026, 8, 31, tzinfo=UTC),
    )

    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        @staticmethod
        def get_ncp(
            ncp_id: int,
            person_identifier: str,
        ) -> NutritionCareProcess | None:
            assert person_identifier == "person-1"
            return ncp if ncp_id == ncp.id else None

    monkeypatch.setattr(get, "NCPRepo", Repository)

    output = NCPGetCommandController(session=object()).run(  # ty: ignore[invalid-argument-type]
        NCPGetOptions(ncp_id=1, person_identifier="person-1"),
    )

    assert output.result.ncp is ncp


def test_get_controller_rejects_unknown_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        @staticmethod
        def get_ncp(_ncp_id: int, _person_identifier: str) -> None:
            return None

    monkeypatch.setattr(get, "NCPRepo", Repository)

    with pytest.raises(LookupError, match="was not found"):
        NCPGetCommandController(session=object()).run(  # ty: ignore[invalid-argument-type]
            NCPGetOptions(ncp_id=999, person_identifier="person-1"),
        )
