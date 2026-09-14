from __future__ import annotations

import asyncio
import typing

from ntk.controllers.ncp import sync
from ntk.controllers.ncp.sync import NCPSyncController
from ntk.pipelines.ncp import NCPSyncResult


def test_sync_controller_uses_persisted_notes_without_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = NCPSyncResult(scanned=3, ncps_created=1)

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Service:
        def __init__(
            self,
            clinical_note_repository: Repository,
        ) -> None:
            assert isinstance(clinical_note_repository, Repository)

        @staticmethod
        async def sync_ncps() -> NCPSyncResult:
            return result

    monkeypatch.setattr(sync, "ClinicalNoteRepo", Repository)
    monkeypatch.setattr(sync, "NutritionCareProcessPipeline", Service)

    output = asyncio.run(
        NCPSyncController(
            session="session",  # ty: ignore[invalid-argument-type]
        ).run(sync.NCPSyncOptions()),
    )

    assert output.result is result


if typing.TYPE_CHECKING:
    import pytest
