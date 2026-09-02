from __future__ import annotations

import inspect
import typing
from datetime import UTC, datetime

import pytest

from ntk.models.sql.resident import ExtractionStatus, ResidentProgressNote
from ntk.services.resident_data.extract.pcc_progress_notes import (
    PccProgressNotesExtractor,
)
from ntk.services.resident_data.extract.unknown_file import UnknownFileExtractor
from ntk.services.resident_data.resident_ingestion_service import (
    ResidentIngestionService,
)

if typing.TYPE_CHECKING:
    import pathlib

    from ntk.repositories.progress_note_repo import ProgressNoteRepo
    from ntk.services.resident_data.resident_resolver import ResidentResolver


def test_constructor_exposes_only_supported_dependencies() -> None:
    parameters = inspect.signature(ResidentIngestionService).parameters

    assert list(parameters) == [
        "knowledge_repository",
        "progress_note_repository",
        "resident_resolver",
    ]


def test_fact_transformer_receives_resolver_directly() -> None:
    resident_resolver = typing.cast("ResidentResolver", object())
    service = ResidentIngestionService(resident_resolver=resident_resolver)

    transformer = service._fact_transformer()  # noqa: SLF001

    assert transformer.resident_resolver is resident_resolver
    assert not hasattr(service, "_resolve_resident_id")


@pytest.mark.anyio
async def test_progress_note_ingestion_passes_repositories_and_resolver(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Resolver:
        @staticmethod
        def resolve_or_create_progress_note(_note: object) -> typing.Never:
            raise AssertionError

    progress_note_repository = typing.cast("ProgressNoteRepo", object())
    resident_resolver = typing.cast("ResidentResolver", Resolver())
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")

    async def extract() -> list[typing.Never]:
        assert extractor.progress_note_repository is progress_note_repository
        assert (
            extractor.resident_resolver
            == resident_resolver.resolve_or_create_progress_note
        )
        return []

    monkeypatch.setattr(extractor, "extract", extract)
    service = ResidentIngestionService(
        progress_note_repository=progress_note_repository,
        resident_resolver=resident_resolver,
    )
    monkeypatch.setattr(service, "_find_extractor", lambda _path: extractor)

    assert await service._extract_report(extractor.path) == []  # noqa: SLF001


@pytest.mark.anyio
async def test_progress_note_ingestion_requires_resolver(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")
    service = ResidentIngestionService(
        progress_note_repository=typing.cast("ProgressNoteRepo", object()),
    )
    monkeypatch.setattr(service, "_find_extractor", lambda _path: extractor)

    with pytest.raises(RuntimeError, match="resident resolver"):
        await service._extract_report(extractor.path)  # noqa: SLF001


@pytest.mark.anyio
async def test_progress_note_status_changes_after_fact_persistence(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    path = tmp_path / "notes.pdf"
    path.write_bytes(b"progress notes")
    note = ResidentProgressNote(
        id=1,
        resident_id=7,
        note_date=datetime(2026, 8, 20, tzinfo=UTC),
        note_text="Resident's appetite remains stable.",
        raw_text="Resident's appetite remains stable.",
        note_key="note-key",
        extraction_status=ExtractionStatus.PENDING,
    )
    extractor = PccProgressNotesExtractor(path)
    extractor.processed_progress_notes.append(note)

    class ResidentRepository:
        @staticmethod
        def document_exists(_checksum: str) -> bool:
            return False

        @staticmethod
        def load_transformed_documents(_documents: object) -> None:
            events.append("facts persisted")

    class Resolver:
        resident_repository = ResidentRepository()

    class ProgressNoteRepository:
        @staticmethod
        def set_extraction_status(
            progress_note: ResidentProgressNote,
            status: ExtractionStatus,
        ) -> ResidentProgressNote:
            assert events == ["facts persisted"]
            progress_note.extraction_status = status
            events.append("note extracted")
            return progress_note

    service = ResidentIngestionService(
        progress_note_repository=typing.cast(
            "ProgressNoteRepo",
            ProgressNoteRepository(),
        ),
        resident_resolver=typing.cast("ResidentResolver", Resolver()),
    )

    async def extract_report(_path: pathlib.Path) -> list[typing.Never]:
        return []

    monkeypatch.setattr(service, "_extract_report", extract_report)
    monkeypatch.setattr(service, "_find_extractor", lambda _path: extractor)

    await service.ingest([path])

    assert events == ["facts persisted", "note extracted"]
    assert note.extraction_status is ExtractionStatus.EXTRACTED


@pytest.mark.anyio
async def test_existing_document_is_skipped_before_extraction(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "existing.pdf"
    path.write_bytes(b"existing document")
    events: list[str] = []

    class ResidentRepository:
        @staticmethod
        def document_exists(_checksum: str) -> bool:
            events.append("existence checked")
            return True

        @staticmethod
        def load_transformed_documents(_documents: object) -> None:
            message = "existing documents must not be loaded"
            raise AssertionError(message)

    class Resolver:
        resident_repository = ResidentRepository()

    service = ResidentIngestionService(
        resident_resolver=typing.cast("ResidentResolver", Resolver()),
    )

    async def extract_report(_path: pathlib.Path) -> list[typing.Never]:
        message = "existing documents must not be extracted"
        raise AssertionError(message)

    monkeypatch.setattr(service, "_extract_report", extract_report)

    result = await service.ingest([path])

    assert result.documents == []
    assert events == ["existence checked"]


@pytest.mark.anyio
async def test_duplicate_content_is_extracted_once_per_request(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_path = tmp_path / "first.pdf"
    second_path = tmp_path / "second.pdf"
    first_path.write_bytes(b"same document")
    second_path.write_bytes(b"same document")
    extractor = PccProgressNotesExtractor(first_path)
    extraction_calls: list[pathlib.Path] = []
    loaded_document_counts: list[int] = []

    class ResidentRepository:
        @staticmethod
        def document_exists(_checksum: str) -> bool:
            return False

        @staticmethod
        def load_transformed_documents(documents: typing.Sequence[object]) -> None:
            loaded_document_counts.append(len(documents))

    class Resolver:
        resident_repository = ResidentRepository()

    service = ResidentIngestionService(
        resident_resolver=typing.cast("ResidentResolver", Resolver()),
    )

    async def extract_report(path: pathlib.Path) -> list[typing.Never]:
        extraction_calls.append(path)
        return []

    monkeypatch.setattr(service, "_extract_report", extract_report)
    monkeypatch.setattr(service, "_find_extractor", lambda _path: extractor)

    result = await service.ingest([first_path, second_path])

    assert extraction_calls == [first_path]
    assert len(result.documents) == 1
    assert loaded_document_counts == [1]


@pytest.mark.anyio
async def test_unknown_document_ingestion_passes_resolver(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "unknown.pdf"
    path.write_bytes(b"unknown")
    resident_resolver = typing.cast("ResidentResolver", object())
    extractor = UnknownFileExtractor(path)

    async def extract() -> list[typing.Never]:
        assert extractor.resident_resolver is resident_resolver
        return []

    monkeypatch.setattr(extractor, "extract", extract)
    service = ResidentIngestionService(resident_resolver=resident_resolver)
    monkeypatch.setattr(service, "_find_extractor", lambda _path: extractor)

    assert await service._extract_report(path) == []  # noqa: SLF001
