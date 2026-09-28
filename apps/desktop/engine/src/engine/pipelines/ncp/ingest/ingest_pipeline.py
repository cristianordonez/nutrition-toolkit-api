"""Workflow for ingesting deidentified NCP notes as retrieval style examples.

A PCC clinical-note report is parsed for its nutrition notes only. Each note
becomes an ``ncp_note`` row with status ``example`` and no person or facility,
and is embedded so note generation can retrieve it. Nothing else in the report
is kept: no document, clinical source, person or clinical fact is created.

Note text is scrubbed of identifiers that survive redaction before it is
stored or embedded, and short notes that only point elsewhere ("see
assessment", "RD note in UDA") are dropped: they carry no reasoning to imitate.
"""

from __future__ import annotations

import pathlib
import typing
from tempfile import TemporaryDirectory

from pydantic import BaseModel

from engine.models.ncp_note import NCPNoteType
from engine.models.sql.ncp_note import NCPNote
from engine.pipelines.ncp.ingest.deidentify import NoteDeidentifier
from engine.pipelines.person.ingestion.extract.pcc_progress_notes import (
    PccProgressNotesExtractor,
)
from engine.repositories.ncp_note_repo import NCPNoteRepo
from engine.services.embedding_service import EmbeddingService

if typing.TYPE_CHECKING:
    from sqlmodel import Session

    from engine.controllers.uploads import ReadableUpload
    from engine.pipelines.person.ingestion.extract.pcc_progress_notes import (
        ParsedProgressNote,
    )

#: Checked in order against the PCC note type, then the opening of the note.
#: Readmission precedes admission because one contains the other.
_NOTE_TYPE_KEYWORDS: tuple[tuple[NCPNoteType, tuple[str, ...]], ...] = (
    (NCPNoteType.READMISSION, ("readmission", "re-admission", "readmit")),
    (NCPNoteType.ADMISSION, ("admission", "initial nutrition")),
    (NCPNoteType.ANNUAL, ("annual",)),
    (NCPNoteType.QUARTERLY, ("quarterly",)),
    (NCPNoteType.SIGNIFICANT_CHANGE, ("significant change", "sig change")),
    (NCPNoteType.PAYER_CHANGE, ("payer change", "pay source change")),
    (NCPNoteType.WOUND, ("wound",)),
    (NCPNoteType.HIGH_RISK, ("high risk",)),
)

#: How much of a note's text is searched for its type when the PCC note type
#: is generic (e.g. "Dietitian Progress Note"). The type is stated up front.
_TYPE_HINT_CHARS = 200

#: Notes shorter than this, after cleaning, only point at another document
#: ("Dietary UDA completed", "see RD assessment") and make useless examples.
_MIN_EXAMPLE_CHARS = 300


class InvalidClinicalNoteReportError(ValueError):
    """Raised when an ncp-ingest file is not a PCC clinical-note report."""


class NCPIngestSummary(BaseModel):
    """What one report contributed to the example set."""

    notes_found: int
    notes_ingested: int
    duplicates_skipped: int
    pointer_notes_skipped: int = 0


class NCPIngestPipeline:
    """Load deidentified nutrition notes from a PCC report as NCP examples."""

    def __init__(
        self,
        notes: NCPNoteRepo,
        embeddings: EmbeddingService,
        deidentifier: NoteDeidentifier | None = None,
    ) -> None:
        """Store the example repository, embedding model and text scrubber."""
        self.notes = notes
        self.embeddings = embeddings
        self.deidentifier = deidentifier or NoteDeidentifier()

    @classmethod
    def from_session(cls, session: Session) -> NCPIngestPipeline:
        """Build the ingest workflow from one request or CLI database session."""
        return cls(NCPNoteRepo(session), EmbeddingService(session))

    async def run_upload(self, file: ReadableUpload) -> NCPIngestSummary:
        """Materialize and ingest one uploaded PDF report."""
        filename = pathlib.Path(file.filename or "clinical-notes.pdf").name
        if pathlib.Path(filename).suffix.casefold() != ".pdf":
            message = f"'{filename}' is not a PCC clinical-note report PDF"
            raise InvalidClinicalNoteReportError(message)
        with TemporaryDirectory(prefix="ntk-ncp-ingest-") as directory:
            path = pathlib.Path(directory) / filename
            path.write_bytes(await file.read())
            return await self.run(path)

    async def run(self, path: pathlib.Path) -> NCPIngestSummary:
        """Store and embed each new nutrition note in one report as an example."""
        self._validate_report_path(path)
        extractor = self._clinical_note_report(path)
        parsed = extractor.extract_nutrition_notes(deidentified=True)
        # Scrubbed first so a note is deduplicated, length-checked and embedded
        # on exactly the text that is stored.
        pointer_notes = 0
        by_content: dict[str, ParsedProgressNote] = {}
        for note in parsed:
            content = self.deidentifier.deidentify(note.note_text).strip()
            if len(content) < _MIN_EXAMPLE_CHARS:
                pointer_notes += 1
                continue
            by_content.setdefault(content, note)
        # Deduplicated on content, within the report and against what is
        # already stored, so ingesting the same report twice adds nothing.
        existing = self.notes.existing_example_contents(list(by_content))
        new = {
            content: note
            for content, note in by_content.items()
            if content not in existing
        }
        if new:
            vectors = await self.embeddings.get_embeddings_async(list(new))
            self.notes.add_examples(
                [
                    NCPNote(note_type=classify_note_type(note), content=content)
                    for content, note in new.items()
                ],
                vectors,
                self.embeddings.model,
            )
        return NCPIngestSummary(
            notes_found=len(parsed),
            notes_ingested=len(new),
            duplicates_skipped=len(parsed) - pointer_notes - len(new),
            pointer_notes_skipped=pointer_notes,
        )

    @staticmethod
    def _validate_report_path(path: pathlib.Path) -> None:
        """Require an existing PDF clinical-note report."""
        if not path.is_file():
            message = f"Clinical-note report does not exist: {path}"
            raise ValueError(message)
        if path.suffix.casefold() != ".pdf":
            message = f"Clinical-note report is not a PDF: {path}"
            raise InvalidClinicalNoteReportError(message)

    @staticmethod
    def _clinical_note_report(path: pathlib.Path) -> PccProgressNotesExtractor:
        """Require the PDF to match the PCC clinical-note report format."""
        extractor = PccProgressNotesExtractor(path)
        try:
            is_clinical_note_report = extractor.is_expected_format()
        except RuntimeError as error:
            message = f"'{path.name}' is not a readable PCC clinical-note report"
            raise InvalidClinicalNoteReportError(message) from error
        if not is_clinical_note_report:
            message = f"'{path.name}' is not a PCC clinical-note report"
            raise InvalidClinicalNoteReportError(message)
        return extractor


def classify_note_type(note: ParsedProgressNote) -> NCPNoteType:
    """Map a PCC note to an NCP note type, defaulting to a follow-up."""
    for text in (note.note_type or "", note.note_text[:_TYPE_HINT_CHARS]):
        normalized = " ".join(text.casefold().split())
        for note_type, keywords in _NOTE_TYPE_KEYWORDS:
            if any(keyword in normalized for keyword in keywords):
                return note_type
    return NCPNoteType.FOLLOW_UP


__all__ = [
    "InvalidClinicalNoteReportError",
    "NCPIngestPipeline",
    "NCPIngestSummary",
    "classify_note_type",
]
