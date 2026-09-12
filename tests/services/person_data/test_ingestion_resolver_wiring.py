from __future__ import annotations

import inspect
import typing
from datetime import UTC, datetime

import pytest

from ntk.models.extracted_fact_create import DietPayload, ExtractedFactCreate
from ntk.models.sql.person import ExtractionStatus, PersonProgressNote
from ntk.pipelines.person.ingestion.extract.pcc_progress_notes import (
    ParsedProgressNote,
    PccProgressNotesExtractor,
)
from ntk.pipelines.person.ingestion.extract.unknown_file import UnknownFileExtractor
from ntk.pipelines.person.ingestion.pipeline import (
    PersonIngestionPipeline,
)

if typing.TYPE_CHECKING:
    import pathlib

    from ntk.repositories.progress_note_repo import ProgressNoteRepo
    from ntk.services.person.person_service import PersonService


def test_constructor_exposes_only_supported_dependencies() -> None:
    parameters = inspect.signature(PersonIngestionPipeline).parameters

    assert list(parameters) == [
        "progress_note_repository",
        "person_service",
        "facility_resolver",
    ]


def test_fact_transformer_receives_service_directly() -> None:
    person_service = typing.cast("PersonService", object())
    service = PersonIngestionPipeline(person_service=person_service)

    transformer = service._fact_transformer()  # noqa: SLF001

    assert transformer.person_service is person_service
    assert not hasattr(service, "_resolve_person_id")


def test_non_order_extractors_cannot_persist_a_current_diet(
    tmp_path: pathlib.Path,
) -> None:
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")
    diet_fact = ExtractedFactCreate(
        payload=DietPayload(diet_type="regular"),
        confidence=1,
    )

    filtered = PersonIngestionPipeline._filter_source_owned_facts(  # noqa: SLF001
        extractor,
        [diet_fact],
    )

    assert filtered == []


@pytest.mark.anyio
async def test_progress_note_ingestion_keeps_resolution_in_pipeline(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note = ParsedProgressNote(
        source_person_identifier="R-7",
        note_date=datetime(2026, 8, 20, tzinfo=UTC),
        note_text="Nutrition note",
        raw_text="Nutrition note",
        source_filename="notes.pdf",
    )

    class Repository:
        @staticmethod
        def get_by_key(_note_key: str) -> None:
            return None

        @staticmethod
        def create(progress_note: PersonProgressNote) -> PersonProgressNote:
            progress_note.id = 11
            return progress_note

    class Resolver:
        repository = object()

        @staticmethod
        def resolve_or_create_progress_note(_note: object) -> object:
            return type("ResolvedPerson", (), {"id": 7})()

    progress_note_repository = typing.cast("ProgressNoteRepo", Repository())
    person_service = typing.cast("PersonService", Resolver())
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")

    async def extract_prepared(prepared: list[object]) -> list[typing.Never]:
        assert len(prepared) == 1
        assert prepared[0].person_id == 7  # noqa: PLR2004  # ty: ignore[unresolved-attribute]
        assert prepared[0].progress_note_id == 11  # noqa: PLR2004  # ty: ignore[unresolved-attribute]
        return []

    monkeypatch.setattr(extractor, "extract_notes", lambda: [note])
    monkeypatch.setattr(extractor, "extract_prepared", extract_prepared)
    service = PersonIngestionPipeline(
        progress_note_repository=progress_note_repository,
        person_service=person_service,
    )
    monkeypatch.setattr(service, "_find_extractor", lambda _path: extractor)
    assert await service._extract_report(extractor.path) == []  # noqa: SLF001


@pytest.mark.anyio
async def test_filtered_progress_notes_still_update_header_demographics(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note = ParsedProgressNote(
        source_person_identifier="EN140516",
        source_person_name="Keitt-jones, Bertha",
        date_of_birth=datetime(1944, 8, 7, tzinfo=UTC).date(),
        sex="f",
        note_date=datetime(2026, 9, 9, tzinfo=UTC),
        note_type="Nursing Note",
        note_text="Routine rounds completed.",
        raw_text="Routine rounds completed.",
        source_filename="notes.pdf",
    )
    resolved: list[ParsedProgressNote] = []

    class Repository:
        pass

    class Service:
        repository = Repository()

        @staticmethod
        def resolve_or_create_progress_note(item: ParsedProgressNote) -> object:
            resolved.append(item)
            return type("ResolvedPerson", (), {"id": 7})()

    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")
    extractor._last_parsed_notes = [note]  # noqa: SLF001
    monkeypatch.setattr(extractor, "extract_notes", list)
    service = PersonIngestionPipeline(
        progress_note_repository=typing.cast("ProgressNoteRepo", object()),
        person_service=typing.cast("PersonService", Service()),
    )
    monkeypatch.setattr(service, "_find_extractor", lambda _path: extractor)

    assert await service._extract_report(extractor.path) == []  # noqa: SLF001
    assert resolved == [note]


@pytest.mark.anyio
async def test_progress_note_ingestion_requires_service(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")
    service = PersonIngestionPipeline(
        progress_note_repository=typing.cast("ProgressNoteRepo", object()),
    )
    note = ParsedProgressNote(
        source_person_identifier="R-7",
        note_date=datetime(2026, 8, 20, tzinfo=UTC),
        note_text="Nutrition note",
        raw_text="Nutrition note",
        source_filename="notes.pdf",
    )
    monkeypatch.setattr(extractor, "extract_notes", lambda: [note])
    monkeypatch.setattr(service, "_find_extractor", lambda _path: extractor)
    with pytest.raises(RuntimeError, match="person service"):
        await service._extract_report(extractor.path)  # noqa: SLF001


@pytest.mark.anyio
async def test_progress_note_status_changes_after_fact_persistence(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    path = tmp_path / "notes.pdf"
    path.write_bytes(b"progress notes")
    note = PersonProgressNote(
        id=1,
        person_id=7,
        note_date=datetime(2026, 8, 20, tzinfo=UTC),
        note_text="Person's appetite remains stable.",
        raw_text="Person's appetite remains stable.",
        note_key="note-key",
        extraction_status=ExtractionStatus.PENDING,
    )
    extractor = PccProgressNotesExtractor(path)

    class PersonRepository:
        @staticmethod
        def document_exists(_checksum: str) -> bool:
            return False

        @staticmethod
        def load_transformed_documents(_documents: object) -> None:
            events.append("facts persisted")

    class Service:
        repository = PersonRepository()

    class ProgressNoteRepository:
        @staticmethod
        def set_extraction_status(
            progress_note: PersonProgressNote,
            status: ExtractionStatus,
        ) -> PersonProgressNote:
            assert events == ["facts persisted"]
            progress_note.extraction_status = status
            events.append("note extracted")
            return progress_note

    service = PersonIngestionPipeline(
        progress_note_repository=typing.cast(
            "ProgressNoteRepo",
            ProgressNoteRepository(),
        ),
        person_service=typing.cast("PersonService", Service()),
    )
    service._processed_progress_notes[path.resolve()] = [note]  # noqa: SLF001

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

    class PersonRepository:
        @staticmethod
        def document_exists(_checksum: str) -> bool:
            events.append("existence checked")
            return True

        @staticmethod
        def load_transformed_documents(_documents: object) -> None:
            message = "existing documents must not be loaded"
            raise AssertionError(message)

    class Service:
        repository = PersonRepository()

    service = PersonIngestionPipeline(
        person_service=typing.cast("PersonService", Service()),
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

    class PersonRepository:
        @staticmethod
        def document_exists(_checksum: str) -> bool:
            return False

        @staticmethod
        def load_transformed_documents(documents: typing.Sequence[object]) -> None:
            loaded_document_counts.append(len(documents))

    class Service:
        repository = PersonRepository()

    service = PersonIngestionPipeline(
        person_service=typing.cast("PersonService", Service()),
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
async def test_unknown_document_ingestion_keeps_extractor_persistence_free(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "unknown.pdf"
    path.write_bytes(b"unknown")
    extractor = UnknownFileExtractor(path)

    async def extract() -> list[typing.Never]:
        assert not hasattr(extractor, "person_service")
        return []

    monkeypatch.setattr(extractor, "extract", extract)
    service = PersonIngestionPipeline(
        person_service=typing.cast("PersonService", object()),
    )
    monkeypatch.setattr(service, "_find_extractor", lambda _path: extractor)

    assert await service._extract_report(path) == []  # noqa: SLF001
