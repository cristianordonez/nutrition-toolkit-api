from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from api.controllers.ncp import finalize
from api.controllers.ncp.finalize import (
    NCPFinalizeCommandController,
    NCPFinalizeOptions,
)
from api.models.sql.ncp import NutritionCareProcess, NutritionCareProcessStatus


def test_finalize_controller_returns_updated_ncp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ncp = NutritionCareProcess(
        id=1,
        person_identifier="person-1",
        note_text="Assessment",
        content_hash="hash",
        created_by="model",
        status=NutritionCareProcessStatus.FINALIZED,
        created_at=datetime(2026, 8, 31, tzinfo=UTC),
    )

    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        @staticmethod
        def finalize_ncp(
            ncp_id: int,
            person_identifier: str,
        ) -> NutritionCareProcess | None:
            assert person_identifier == "person-1"
            return ncp if ncp_id == ncp.id else None

        @staticmethod
        def get_embedding(_ncp_id: int) -> object:
            return object()

    monkeypatch.setattr(finalize, "NCPRepo", Repository)

    output = asyncio.run(
        NCPFinalizeCommandController(
            session=object(),  # ty: ignore[invalid-argument-type]
        ).run(NCPFinalizeOptions(ncp_id=1, person_identifier="person-1")),
    )

    assert output.result.ncp is ncp


def test_finalize_controller_rejects_unknown_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        @staticmethod
        def finalize_ncp(_ncp_id: int, _person_identifier: str) -> None:
            return None

    monkeypatch.setattr(finalize, "NCPRepo", Repository)

    with pytest.raises(LookupError, match="was not found"):
        asyncio.run(
            NCPFinalizeCommandController(
                session=object(),  # ty: ignore[invalid-argument-type]
            ).run(NCPFinalizeOptions(ncp_id=999, person_identifier="person-1")),
        )
