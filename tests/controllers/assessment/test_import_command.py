from __future__ import annotations

import asyncio
import typing
from datetime import date
from types import SimpleNamespace

import pytest

from ntk.controllers.assessment import import_assessments as import_module
from ntk.controllers.assessment.import_assessments import (
    AssessmentImportController,
    AssessmentImportOptions,
)
from ntk.models.sql.resident import AssessmentSource, ResidentAssessment

if typing.TYPE_CHECKING:
    import pathlib


def test_import_command_ingests_notes_then_synchronizes_assessments(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = tmp_path / "progress-notes.pdf"
    report.touch()
    assessment = ResidentAssessment(
        resident_id=1,
        content="Nutrition assessment",
        content_hash="hash",
        assessment_date=date(2026, 8, 28),
        created_by="dietitian",
        assessment_source=AssessmentSource.IMPORTED,
    )
    events: list[str] = []

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Resolver:
        def __init__(self, **repositories: object) -> None:
            assert set(repositories) == {
                "facility_repository",
                "resident_repository",
                "stay_repository",
            }

    class IngestionService:
        def __init__(
            self,
            *,
            progress_note_repository: Repository,
            resident_resolver: Resolver,
        ) -> None:
            self.progress_note_repository = progress_note_repository
            assert isinstance(resident_resolver, Resolver)

        async def ingest(self, paths: list[pathlib.Path]) -> None:
            assert paths == [report]
            events.append("notes ingested")

    class SyncService:
        def __init__(
            self,
            progress_note_repository: Repository,
            assessment_repository: Repository,
        ) -> None:
            assert isinstance(progress_note_repository, Repository)
            assert isinstance(assessment_repository, Repository)

        @staticmethod
        async def sync_assessments() -> object:
            assert events == ["notes ingested"]
            events.append("assessments synchronized")
            return SimpleNamespace(created_assessments=[assessment])

    monkeypatch.setattr(import_module, "AssessmentRepo", Repository)
    monkeypatch.setattr(import_module, "FacilityRepo", Repository)
    monkeypatch.setattr(import_module, "ProgressNoteRepo", Repository)
    monkeypatch.setattr(import_module, "ResidentFacilityStayRepo", Repository)
    monkeypatch.setattr(import_module, "ResidentRepo", Repository)
    monkeypatch.setattr(import_module, "ResidentResolver", Resolver)
    monkeypatch.setattr(import_module, "ResidentIngestionService", IngestionService)
    monkeypatch.setattr(import_module, "AssessmentSyncService", SyncService)

    output = asyncio.run(
        AssessmentImportController(
            session="session",  # ty: ignore[invalid-argument-type]
        ).run(AssessmentImportOptions(path=report)),
    )

    assert events == ["notes ingested", "assessments synchronized"]
    assert output.result.assessments == [assessment]
    assert output.result.to_console() == str(assessment.id)


def test_import_command_rejects_non_pdf(tmp_path: pathlib.Path) -> None:
    report = tmp_path / "progress-notes.txt"
    report.touch()

    with pytest.raises(ValueError, match="is not a PDF"):
        asyncio.run(
            AssessmentImportController(
                session="session",  # ty: ignore[invalid-argument-type]
            ).run(AssessmentImportOptions(path=report)),
        )
