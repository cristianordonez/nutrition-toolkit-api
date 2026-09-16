from __future__ import annotations

import asyncio
import typing
from datetime import UTC, datetime

from api.models.sql.ncp import (
    NutritionCareProcess,
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
)
from api.presentation.api.routers import nutrition_care_processes
from ntk.models.ncp_public import NutritionCareProcessPublic

if typing.TYPE_CHECKING:
    import pytest


def _ncp() -> NutritionCareProcess:
    return NutritionCareProcess(
        id=1,
        person_identifier="R1",
        facility_identifier="FAC-1",
        note_text="Nutrition assessment",
        content_hash="hash",
        created_by="model",
        ncp_source=NutritionCareProcessSource.IMPORTED,
        source_filename="report.pdf",
        status=NutritionCareProcessStatus.FINALIZED,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


def test_get_ncp_returns_the_public_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ncp = _ncp()

    class Service:
        def __init__(self, _repository: object) -> None:
            pass

        @staticmethod
        def get(ncp_id: int, person_identifier: str) -> NutritionCareProcess | None:
            assert ncp_id == 1
            assert person_identifier == "R1"
            return ncp

    monkeypatch.setattr(nutrition_care_processes, "NCPRepo", lambda session: session)
    monkeypatch.setattr(
        nutrition_care_processes,
        "NutritionCareProcessService",
        Service,
    )

    result = asyncio.run(
        nutrition_care_processes.get_ncp(1, "R1", "session"),  # ty: ignore[invalid-argument-type]
    )

    assert isinstance(result, NutritionCareProcessPublic)
    assert result.id == 1
    assert result.note_text == "Nutrition assessment"
    assert not hasattr(result, "ncp_source")
    assert not hasattr(result, "source_filename")


def test_list_ncps_returns_public_projections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ncp = _ncp()

    class Service:
        def __init__(self, _repository: object) -> None:
            pass

        @staticmethod
        def list_ncps(person_identifier: str) -> list[NutritionCareProcess]:
            assert person_identifier == "R1"
            return [ncp]

    monkeypatch.setattr(nutrition_care_processes, "NCPRepo", lambda session: session)
    monkeypatch.setattr(
        nutrition_care_processes,
        "NutritionCareProcessService",
        Service,
    )

    result = asyncio.run(
        nutrition_care_processes.list_ncps("R1", "session"),  # ty: ignore[invalid-argument-type]
    )

    assert result == [NutritionCareProcessPublic.model_validate(ncp)]
    assert all(isinstance(item, NutritionCareProcessPublic) for item in result)
