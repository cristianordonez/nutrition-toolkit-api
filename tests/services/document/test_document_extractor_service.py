from __future__ import annotations

import typing
from datetime import UTC, datetime
from hashlib import sha256

import pymupdf
import pytest

from ntk.models.knowledge import KnowledgeType
from ntk.models.sql.assessment import Assessment, AssessmentSource
from ntk.models.sql.resident import ProgressNote, SourceReference
from ntk.services.document import DocumentExtractorService
from ntk.services.document.document_extractor_service import load_extractors

if typing.TYPE_CHECKING:
    import pathlib


def _extractor_type(name: str) -> type:
    return next(
        extractor_type
        for extractor_type in load_extractors()
        if extractor_type.__name__ == name
    )


def _write_pdf(path: pathlib.Path, text: str) -> None:
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), text)
        document.save(path)


def test_find_extractor_returns_first_matching_format(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "progress-notes.pdf"
    path.touch()
    expected_type = _extractor_type("PccProgressNotesExtractor")
    monkeypatch.setattr(
        "ntk.services.document.extractors.base.BaseExtractor._first_page_text",
        "Progress Notes *NEW*",
    )
    extractor = DocumentExtractorService.find_extractor(path)
    assert type(extractor) is expected_type
    assert extractor is not None
    assert extractor.path == path


def test_find_extractor_returns_none_for_unknown_format(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "unknown.pdf"
    _write_pdf(path, "Unrecognized report")
    extractor = DocumentExtractorService.find_extractor(path)
    assert extractor is None


def test_find_extractor_rejects_missing_file(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "missing.pdf"

    with pytest.raises(ValueError, match="does not exist"):
        DocumentExtractorService.find_extractor(path)


def test_create_assessment_from_progress_note_maps_content_and_metadata() -> None:
    note_date = datetime(2026, 8, 23, 14, 30, tzinfo=UTC)
    note = ProgressNote(
        note_date=note_date,
        note_type="Nutrition",
        author="  Jane Doe, RD  ",
        note_text="  Nutrition assessment\nwith plan  ",
        raw_text="raw report text",
        source=SourceReference(
            source_type="PCC Progress Notes *NEW* Report",
            source="progress-notes.pdf",
            extracted_at=note_date,
        ),
    )

    assessment = DocumentExtractorService.create_assessment_from_progress_note(
        note,
        assessment_index=4,
    )

    assert assessment.content == "Nutrition assessment\nwith plan"
    assert assessment.source is AssessmentSource.UPLOADED
    assert assessment.source_filename == "progress-notes.pdf"
    assert (
        assessment.content_hash
        == sha256(
            b"Nutrition assessment with plan",
        ).hexdigest()
    )
    assert assessment.assessment_index == 4  # noqa: PLR2004
    assert assessment.assessment_date == note_date.date()
    assert assessment.created_by == "Jane Doe, RD"


def test_create_assessment_from_progress_note_uses_overrides_and_validates() -> None:
    extracted_at = datetime(2026, 8, 23, tzinfo=UTC)
    note = ProgressNote(
        author=None,
        note_text="Assessment",
        raw_text="Assessment",
        source=SourceReference(
            source_type="progress-note",
            extracted_at=extracted_at,
        ),
    )

    assessment = DocumentExtractorService.create_assessment_from_progress_note(
        note,
        assessment_source=AssessmentSource.GENERATED,
        created_by="  importer  ",
    )

    assert assessment.source is AssessmentSource.GENERATED
    assert assessment.created_by == "importer"
    assert assessment.source_filename is None
    assert assessment.assessment_date is None

    with pytest.raises(ValueError, match="cannot be empty"):
        DocumentExtractorService.create_assessment_from_progress_note(
            note.model_copy(update={"note_text": "  "}),
        )


def test_assessment_ingest_converts_notes_and_embeds_content(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "progress-notes.pdf"
    path.touch()
    extracted_at = datetime(2026, 8, 23, tzinfo=UTC)
    notes = [
        ProgressNote(
            author="RD",
            note_text=text,
            raw_text=text,
            source=SourceReference(
                source_type="progress-note",
                source=path.name,
                extracted_at=extracted_at,
            ),
        )
        for text in ("First assessment", "Second assessment")
    ]

    class OpenAI:
        embedding_model = "embedding-model"
        calls = 0

        @classmethod
        def get_embedding(cls, contents: str) -> list[float]:
            assert contents in {"First assessment", "Second assessment"}
            cls.calls += 1
            return [float(cls.calls)]

    class Repository:
        @staticmethod
        def ingest(
            assessments: list[Assessment],
            embeddings: list[list[float]],
            model_name: str,
            *,
            overwrite: bool,
        ) -> list[Assessment]:
            assert embeddings == [[1.0], [2.0]]
            assert model_name == "embedding-model"
            assert overwrite is True
            return assessments

    service = DocumentExtractorService(
        assessment_repository=Repository(),  # ty: ignore[invalid-argument-type]
        open_ai_service=OpenAI(),  # ty: ignore[invalid-argument-type]
    )
    monkeypatch.setattr(service, "get_progress_notes_from_report", lambda _path: notes)

    assessments = service.ingest_assessment(
        path,
        created_by="facility-rd",
        overwrite=True,
    )

    assert [assessment.assessment_index for assessment in assessments] == [0, 1]
    assert all(assessment.created_by == "facility-rd" for assessment in assessments)


def test_knowledge_ingest_rejects_missing_chunks(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "knowledge.pdf"
    _write_pdf(path, "Diet Manual")
    extractor_type = _extractor_type("DietManualExtractor")
    monkeypatch.setattr(extractor_type, "extract", lambda _self: None)

    class Repository:
        @staticmethod
        def find_existing_knowledge(
            _knowledge_type: KnowledgeType,
            _file_hash: str,
        ) -> None:
            return None

    with pytest.raises(NotImplementedError, match="not implemented"):
        DocumentExtractorService(
            knowledge_repository=Repository(),  # ty: ignore[invalid-argument-type]
        ).ingest_knowledge(path, KnowledgeType.DIET_MANUAL)


def test_create_knowledge_uses_file_identity(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "manual.pdf"
    path.write_bytes(b"manual")

    extractor_type = _extractor_type("NutritionCareManualExtractor")
    knowledge = extractor_type(path).create_knowledge()

    assert knowledge.filename == path.name
    assert knowledge.knowledge_type is KnowledgeType.NUTRITION_CARE_MANUAL
    assert knowledge.file_hash == sha256(b"manual").hexdigest()
