from __future__ import annotations

import asyncio
import typing

import pymupdf
import pytest
from sqlalchemy import select as sql_select
from sqlmodel import Session, col, select

from engine.database.bootstrap import upgrade_database
from engine.database.db import create_database_engine
from engine.database.vectors import EMBEDDING_DIMENSIONS, ncp_vectors
from engine.models.ncp_note import NCPNoteStatus, NCPNoteType
from engine.models.sql.clinical_source import ClinicalSource
from engine.models.sql.document import Document
from engine.models.sql.ncp_note import NCPNote
from engine.models.sql.person import Person
from engine.pipelines.ncp.ingest.ingest_pipeline import (
    InvalidClinicalNoteReportError,
    NCPIngestPipeline,
    classify_note_type,
)
from engine.pipelines.person.ingestion.extract.pcc_progress_notes import (
    ParsedProgressNote,
    PccProgressNotesExtractor,
)
from engine.repositories.ncp_note_repo import NCPNoteRepo
from engine.services.embedding_service import EmbeddingService

if typing.TYPE_CHECKING:
    import pathlib


class _StubEmbeddings(EmbeddingService):
    """Embed deterministically without loading the real model."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.embedding_model = "stub-model"
        self.calls: list[list[str]] = []

    def get_embeddings(self, contents: list[str]) -> list[list[float]]:
        self.calls.append(contents)
        return [
            [float(len(content)), 1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 2)
            for content in contents
        ]


def _session() -> Session:
    engine = create_database_engine("sqlite://")
    upgrade_database(engine)
    return Session(engine)


def _write_pdf(path: pathlib.Path, text: str) -> None:
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), text)
        document.save(path)


def _report(tmp_path: pathlib.Path) -> pathlib.Path:
    report = tmp_path / "progress-notes.pdf"
    _write_pdf(report, "Progress Notes *NEW*")
    return report


#: Pads a note past the pointer-note threshold with clinical-sounding text.
_BODY = (
    " Intake of meals averages 75-100% with good appetite reported by staff."
    " No chewing or swallowing difficulty noted; tolerating current texture."
    " Skin intact per nursing. Labs reviewed and within normal limits for age."
    " Will continue current plan of care and monitor weights monthly."
    " RD available as needed."
)


def _note(note_type: str, text: str) -> ParsedProgressNote:
    return ParsedProgressNote(
        note_type=note_type,
        note_text=text,
        raw_text=text,
        source_filename="progress-notes.pdf",
    )


@pytest.fixture
def parsed_notes(monkeypatch: pytest.MonkeyPatch) -> list[ParsedProgressNote]:
    """Stand in for the PDF parser; the report format check stays real."""
    notes: list[ParsedProgressNote] = []

    def extract(
        _self: PccProgressNotesExtractor,
        *,
        deidentified: bool = False,
    ) -> list[ParsedProgressNote]:
        assert deidentified, "deidentified reports have no identity to parse"
        return notes

    monkeypatch.setattr(PccProgressNotesExtractor, "extract_nutrition_notes", extract)
    return notes


def _pipeline(session: Session) -> tuple[NCPIngestPipeline, _StubEmbeddings]:
    embeddings = _StubEmbeddings(session)
    return NCPIngestPipeline(NCPNoteRepo(session), embeddings), embeddings


def test_ingest_stores_embedded_examples_only(
    tmp_path: pathlib.Path,
    parsed_notes: list[ParsedProgressNote],
) -> None:
    parsed_notes.extend(
        [
            _note("Dietary - Quarterly Review", "Quarterly review." + _BODY),
            _note("Dietitian Progress Note", "Annual nutrition assessment." + _BODY),
        ],
    )
    with _session() as session:
        pipeline, _ = _pipeline(session)

        summary = asyncio.run(pipeline.run(_report(tmp_path)))

        notes = session.exec(select(NCPNote).order_by(col(NCPNote.id))).all()
        assert summary.notes_ingested == 2  # noqa: PLR2004
        assert [note.status for note in notes] == [NCPNoteStatus.EXAMPLE] * 2
        assert [note.note_type for note in notes] == [
            NCPNoteType.QUARTERLY,
            NCPNoteType.ANNUAL,
        ]
        assert all(note.person_id is None for note in notes)
        assert all(note.facility_id is None for note in notes)
        vectors = (
            session.connection()
            .execute(
                sql_select(ncp_vectors.c.ncp_note_id).where(
                    ncp_vectors.c.model == "stub-model",
                ),
            )
            .all()
        )
        assert sorted(row[0] for row in vectors) == [note.id for note in notes]
        # Nothing from the person-ingestion path is created.
        for table in (Document, ClinicalSource, Person):
            assert session.exec(select(table)).first() is None


def test_reingesting_a_report_adds_nothing(
    tmp_path: pathlib.Path,
    parsed_notes: list[ParsedProgressNote],
) -> None:
    parsed_notes.extend(
        [
            _note("Nutrition/Dietary Note", "Follow up." + _BODY),
            _note("Nutrition/Dietary Note", "Follow up." + _BODY),
        ],
    )
    with _session() as session:
        pipeline, embeddings = _pipeline(session)
        report = _report(tmp_path)

        first = asyncio.run(pipeline.run(report))
        second = asyncio.run(pipeline.run(report))

        assert (first.notes_ingested, first.duplicates_skipped) == (1, 1)
        assert (second.notes_ingested, second.duplicates_skipped) == (0, 2)
        assert embeddings.calls == [["Follow up." + _BODY]]
        assert len(session.exec(select(NCPNote)).all()) == 1


def test_ingest_drops_pointer_notes(
    tmp_path: pathlib.Path,
    parsed_notes: list[ParsedProgressNote],
) -> None:
    parsed_notes.extend(
        [
            _note("Dietitian Progress Note", "See Dietary UDA for assessment."),
            _note("Dietitian Progress Note", "Follow up." + _BODY),
        ],
    )
    with _session() as session:
        pipeline, embeddings = _pipeline(session)

        summary = asyncio.run(pipeline.run(_report(tmp_path)))

        assert (
            summary.notes_found,
            summary.notes_ingested,
            summary.pointer_notes_skipped,
            summary.duplicates_skipped,
        ) == (2, 1, 1, 0)
        assert embeddings.calls == [["Follow up." + _BODY]]


def test_ingest_stores_and_embeds_deidentified_text(
    tmp_path: pathlib.Path,
    parsed_notes: list[ParsedProgressNote],
) -> None:
    parsed_notes.append(
        _note(
            "Dietitian Progress Note",
            "Quarterly review. Spoke with son/Samit about diet." + _BODY,
        ),
    )
    with _session() as session:
        pipeline, embeddings = _pipeline(session)

        asyncio.run(pipeline.run(_report(tmp_path)))

        stored = session.exec(select(NCPNote)).one().content
        assert "Samit" not in stored
        assert "son [NAME]" in stored
        assert embeddings.calls == [[stored]]


def test_ingest_rejects_non_pdf(tmp_path: pathlib.Path) -> None:
    report = tmp_path / "progress-notes.txt"
    report.touch()

    with (
        _session() as session,
        pytest.raises(
            InvalidClinicalNoteReportError,
            match="is not a PDF",
        ),
    ):
        asyncio.run(_pipeline(session)[0].run(report))


def test_ingest_rejects_pdf_that_is_not_clinical_note_report(
    tmp_path: pathlib.Path,
) -> None:
    report = tmp_path / "orders.pdf"
    _write_pdf(report, "Order Listing Report")

    with (
        _session() as session,
        pytest.raises(
            InvalidClinicalNoteReportError,
            match="is not a PCC clinical-note report",
        ),
    ):
        asyncio.run(_pipeline(session)[0].run(report))


@pytest.mark.parametrize(
    ("note_type", "text", "expected"),
    [
        ("Dietary Readmission Assessment", "", NCPNoteType.READMISSION),
        ("Dietary Admission Assessment", "", NCPNoteType.ADMISSION),
        ("Nutrition - Significant Change", "", NCPNoteType.SIGNIFICANT_CHANGE),
        (
            "Dietitian Progress Note",
            "Quarterly nutrition review.",
            NCPNoteType.QUARTERLY,
        ),
        ("Dietitian Progress Note", "Wound follow-up.", NCPNoteType.WOUND),
        ("Dietitian Progress Note", "Intake good.", NCPNoteType.FOLLOW_UP),
    ],
)
def test_note_type_is_read_from_type_then_text(
    note_type: str,
    text: str,
    expected: NCPNoteType,
) -> None:
    assert classify_note_type(_note(note_type, text or "Note.")) is expected
