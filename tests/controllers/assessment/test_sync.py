from __future__ import annotations

import asyncio
import typing

from ntk.controllers.assessment import sync
from ntk.controllers.assessment.sync import AssessmentSyncController
from ntk.pipelines.assessment import AssessmentSyncResult


def test_sync_controller_uses_persisted_notes_without_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = AssessmentSyncResult(scanned=3, assessments_created=1)

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Service:
        def __init__(
            self,
            assessments: Repository,
            *,
            progress_note_repository: Repository,
        ) -> None:
            assert isinstance(progress_note_repository, Repository)
            assert isinstance(assessments, Repository)

        @staticmethod
        async def sync_assessments() -> AssessmentSyncResult:
            return result

    monkeypatch.setattr(sync, "ProgressNoteRepo", Repository)
    monkeypatch.setattr(sync, "AssessmentRepo", Repository)
    monkeypatch.setattr(sync, "AssessmentPipeline", Service)

    output = asyncio.run(
        AssessmentSyncController(
            session="session",  # ty: ignore[invalid-argument-type]
        ).run(sync.AssessmentSyncOptions()),
    )

    assert output.result is result


if typing.TYPE_CHECKING:
    import pytest
