from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
import typing
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

import pymupdf
from pydantic import BaseModel

from ntk.agents.data_extraction_agent import (
    DATA_EXTRACTION_MODEL,
    DataExtractionAgent,
    ExtractedClinicalFacts,
    ExtractionInput,
)
from ntk.models.extracted_fact_create import ExtractedFactCreate
from ntk.models.settings import SETTINGS
from ntk.models.sql.resident import ExtractionStatus, ResidentProgressNote

from .base import BaseExtractor
from .registry import register_extractor

if typing.TYPE_CHECKING:
    import pathlib

    from ntk.models.ai_extraction import AIExtractedClinicalFact
    from ntk.repositories.progress_note_repo import ProgressNoteRepo
    from ntk.services.resident_data.resident_resolver import ResidentResolution


class ProgressNoteResidentResolver(typing.Protocol):
    """Resolve the persisted identity associated with a progress note."""

    def __call__(
        self,
        note: ParsedProgressNote,
        /,
    ) -> ResidentResolution | None:
        """Return the resolved resident identity for ``note``."""
        ...


logger = logging.getLogger(__name__)


_RESIDENT_ID_RE = re.compile(
    r"\bResident(?:\s+Name)?\s*:\s*(?P<name>[^(]+?)\s*"
    r"\((?P<id>[A-Z]{0,4}\d+)\)",
)
_DOB_RE = re.compile(
    r"\bDOB\s*:?\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})\b",
    flags=re.IGNORECASE,
)
_SEX_RE = re.compile(
    r"\b(?:Sex|Gender)\s*:\s*(?P<sex>Female|Male|F|M)\b",
    flags=re.IGNORECASE,
)
_EFFECTIVE_DATE_RE = re.compile(
    r"^Effective Date\s*:\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})",
    flags=re.IGNORECASE,
)
_PAGE_RE = re.compile(r"(?m)^Page \d+ of \d+\s*$")
_TRAILING_SIGNATURE_RE = re.compile(
    r"(?ms)\n?Author:.*?\[e-SIGNED\]\s*Signature:\s*(?:\*+|_+)\s*$",
)
_AUTHOR_LINE_RE = re.compile(
    r"^Author\s*:\s*(?P<author>.*?)(?:\s*\[.*)?$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_NOTE_TYPE_RE = re.compile(
    r"Type:\s*(?P<type>.+)$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_NOTE_TEXT_RE = re.compile(
    r"^Note Text\s*:\s*(?P<text>.*)",
    flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
_LINE_Y_TOLERANCE = 2.0
_HEADER_GAP_THRESHOLD = 10.0

NUTRITION_TERMS = {
    "weight",
    "appetite",
    "intake",
    "po intake",
    "diet",
    "supplement",
    "ensure",
    "glucerna",
    "prostat",
    "tube feed",
    "feeding",
    "peg",
    "npo",
    "refused",
    "declined",
    "nausea",
    "vomiting",
    "diarrhea",
    "constipation",
    "edema",
    "dehydration",
    "fluid",
    "sodium",
    "potassium",
    "bun",
    "creatinine",
    "gfr",
    "albumin",
    "a1c",
    "glucose",
    "wound",
    "pressure ulcer",
    "dialysis",
}
_ALWAYS_EXTRACT_NOTE_TYPES = {
    "md progress note",
    "nurse practitioner progress note",
    # Retain compatibility with the spelling used by some PCC facilities.
    "nurse practioner progress note",
    "np/pa progress note",
}
_NUTRITION_FILTERED_NOTE_TYPES = {
    "order note",
    "orders - administration note",
}
_NUTRITION_ASSESSMENT_TYPE_TERMS = (
    "dietary",
    "dietitian",
    "dietician",
    "nutrition",
)
_NUTRITION_TERM_RE = re.compile(
    r"(?<!\w)(?:"
    + "|".join(
        re.escape(term).replace(r"\ ", r"\s+")
        for term in sorted(NUTRITION_TERMS, key=len, reverse=True)
    )
    + r")(?:s|es)?(?!\w)",
    flags=re.IGNORECASE,
)

Word = tuple[float, float, float, float, str, int, int, int]


def clean_note_text(text: str) -> str:
    """Remove repeated author signatures and page markers from note text."""
    text = _PAGE_RE.sub("", text)
    text = _TRAILING_SIGNATURE_RE.sub("", text)
    return text.strip()


class ProgressNoteAction(StrEnum):
    """Action to take after parsing a progress note."""

    FILTER = "filter"
    SEND_TO_AI = "send_to_ai"


class ExtractedNote(BaseModel):
    """Text extracted from one page or one note with source identity."""

    raw_text: str
    page_start: int
    page_end: int
    facility_resident_identifier: str | None = None
    resident_name: str | None = None
    facility_name: str | None = None
    date_of_birth: date | None = None
    sex: str | None = None
    height_in: float | None = None


class ParsedProgressNote(BaseModel):
    facility_resident_identifier: str | None = None
    resident_name: str | None = None
    facility_name: str | None = None
    date_of_birth: date | None = None
    sex: str | None = None
    height_in: float | None = None
    source_page: int | None = None
    note_date: datetime | None = None
    note_type: str | None = None
    author: str | None = None
    note_text: str
    raw_text: str
    source_filename: str


@dataclass(frozen=True, slots=True)
class _PreparedNoteExtraction:
    """Session-free values needed by one concurrent AI extraction task."""

    note: ParsedProgressNote
    resident_id: int
    resident_facility_stay_id: int | None
    progress_note_id: int | None


@register_extractor
class PccProgressNotesExtractor(BaseExtractor):
    """Recognize and extract a PCC progress-notes report."""

    def __init__(
        self,
        path: pathlib.Path,
        progress_note_repository: ProgressNoteRepo | None = None,
        resident_resolver: ProgressNoteResidentResolver | None = None,
        concurrency: int | None = None,
    ) -> None:
        """Initialize the extractor and optional duplicate-note lookup."""
        super().__init__(path)
        resolved_concurrency = (
            SETTINGS.progress_note_extraction_concurrency
            if concurrency is None
            else concurrency
        )
        if resolved_concurrency < 1:
            msg = "Progress-note extraction concurrency must be at least 1"
            raise ValueError(msg)
        self.concurrency = resolved_concurrency
        self.progress_note_repository = progress_note_repository
        self.resident_resolver = resident_resolver
        self.processed_progress_notes: list[ResidentProgressNote] = []
        self.failed_progress_notes: list[ResidentProgressNote] = []

    def is_expected_format(self) -> bool:
        """Return whether the document is a PCC progress-notes report."""
        return self._is_pdf(self.path) and self._first_page_contains(
            "Progress Notes *NEW*",
        )

    async def extract(self) -> list[ExtractedFactCreate]:
        """Send eligible progress-note text to the extraction agent."""
        self.processed_progress_notes.clear()
        self.failed_progress_notes.clear()
        if self.progress_note_repository is None:
            msg = "Must provide progress note repo to class"
            raise RuntimeError(msg)
        eligible_notes = self.extract_notes()
        unique_notes = self._deduplicate_notes(eligible_notes)
        prepared: list[tuple[_PreparedNoteExtraction, ResidentProgressNote]] = []
        for note_key, note in unique_notes:
            progress_note = self._get_or_create_progress_note(note, note_key)
            if progress_note is None:
                continue
            prepared.append(
                (
                    _PreparedNoteExtraction(
                        note=note,
                        resident_id=progress_note.resident_id,
                        resident_facility_stay_id=(
                            progress_note.resident_facility_stay_id
                        ),
                        progress_note_id=progress_note.id,
                    ),
                    progress_note,
                ),
            )

        started_at = time.perf_counter()
        semaphore = asyncio.Semaphore(self.concurrency)
        results = await asyncio.gather(
            *(
                self._extract_prepared_note(note, semaphore)
                for note, _progress_note in prepared
            ),
            return_exceptions=True,
        )
        facts: list[ExtractedFactCreate] = []
        for (_prepared_note, progress_note), result in zip(
            prepared,
            results,
            strict=True,
        ):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, Exception):
                self.progress_note_repository.set_extraction_status(
                    progress_note,
                    ExtractionStatus.FAILED,
                )
                self.failed_progress_notes.append(progress_note)
                logger.error(
                    "Progress-note AI extraction failed for note %s",
                    progress_note.note_key,
                    exc_info=(type(result), result, result.__traceback__),
                )
                continue
            if isinstance(result, BaseException):
                raise result
            facts.extend(result)
            self.processed_progress_notes.append(progress_note)

        logger.info(
            "Progress-note AI extraction completed: notes=%s concurrency=%s "
            "duration_seconds=%.3f successes=%s failures=%s",
            len(prepared),
            self.concurrency,
            time.perf_counter() - started_at,
            len(self.processed_progress_notes),
            len(self.failed_progress_notes),
        )
        return facts

    async def _extract_prepared_note(
        self,
        prepared: _PreparedNoteExtraction,
        semaphore: asyncio.Semaphore,
    ) -> list[ExtractedFactCreate]:
        """Extract one note without accessing a persistence repository."""
        note = prepared.note
        async with semaphore:
            extracted_clinical_facts = await self._run_data_extraction_agent(
                ExtractionInput(
                    text=note.note_text,
                    document_filename=self.path.name,
                    note_date=note.note_date,
                ),
            )
        logger.debug("Extracted AI facts from note: %s", note)
        return [
            self._build_fact_create(
                note,
                ai_fact,
                resident_id=prepared.resident_id,
                resident_facility_stay_id=prepared.resident_facility_stay_id,
                progress_note_id=prepared.progress_note_id,
            )
            for ai_fact in extracted_clinical_facts.facts
        ]

    def _build_fact_from_ai_output(
        self,
        note: ParsedProgressNote,
        progress_note: ResidentProgressNote,
        ai_fact: AIExtractedClinicalFact,
    ) -> ExtractedFactCreate:
        """Build a fact from a progress-note model for compatibility callers."""
        return self._build_fact_create(
            note,
            ai_fact,
            resident_id=progress_note.resident_id,
            resident_facility_stay_id=progress_note.resident_facility_stay_id,
            progress_note_id=progress_note.id,
        )

    @staticmethod
    def _build_fact_create(
        note: ParsedProgressNote,
        ai_fact: AIExtractedClinicalFact,
        *,
        resident_id: int,
        resident_facility_stay_id: int | None,
        progress_note_id: int | None,
    ) -> ExtractedFactCreate:
        """Build the transient fact returned by a session-free worker."""
        logger.debug("AI Fact: %s", ai_fact)
        payload = ai_fact.payload
        if (
            payload.type == "wound"
            and payload.observed_at is None
            and note.note_date is not None
        ):
            payload = payload.model_copy(update={"observed_at": note.note_date})
        return ExtractedFactCreate(
            payload=payload,
            confidence=ai_fact.confidence,
            confidence_reason=ai_fact.confidence_reason,
            model_name=DATA_EXTRACTION_MODEL,
            resident_id=resident_id,
            resident_facility_stay_id=resident_facility_stay_id,
            progress_note_id=progress_note_id,
            facility_resident_identifier=note.facility_resident_identifier,
            resident_name=note.resident_name,
            facility_name=note.facility_name,
            source_page=note.source_page,
        )

    @classmethod
    def _deduplicate_notes(
        cls,
        notes: list[ParsedProgressNote],
    ) -> list[tuple[str, ParsedProgressNote]]:
        """Return the first filtered note for each stable progress-note key."""
        unique_notes: dict[str, ParsedProgressNote] = {}
        for note in notes:
            note_key = cls.get_note_key(
                facility_resident_identifier=note.facility_resident_identifier,
                effective_at=note.note_date,
                note_type=note.note_type,
                author=note.author,
                note_text=note.note_text,
            )
            unique_notes.setdefault(note_key, note)
        duplicate_count = len(notes) - len(unique_notes)
        if duplicate_count:
            logger.info(
                "Removed %s duplicate progress notes before AI extraction",
                duplicate_count,
            )
        return list(unique_notes.items())

    def _get_or_create_progress_note(
        self,
        note: ParsedProgressNote,
        note_key: str,
    ) -> ResidentProgressNote | None:
        """Store an eligible note before sending its text to the AI agent."""
        if self.progress_note_repository is None:
            msg = "Must provide progress note repo during ingestion"
            raise RuntimeError(msg)
        existing = self.progress_note_repository.get_by_key(note_key)
        if existing is not None and self.resident_resolver is not None:
            resolution = self.resident_resolver(note)
            if resolution is None:
                msg = f"Unable to resolve the resident for progress note {note_key}"
                raise ValueError(msg)
            existing = self.progress_note_repository.update_identity(
                existing,
                resident_id=resolution.resident_id,
                resident_facility_stay_id=resolution.resident_facility_stay_id,
            )
        if existing is not None:
            if existing.extraction_status is ExtractionStatus.FAILED:
                self.progress_note_repository.set_extraction_status(
                    existing,
                    ExtractionStatus.PENDING,
                )
            if existing.extraction_status in {
                ExtractionStatus.EXTRACTED,
                ExtractionStatus.SKIPPED,
            }:
                logger.debug(
                    "Skipping completed progress note %s with status %s",
                    note_key,
                    existing.extraction_status,
                )
                return None
            logger.info(
                "Retrying progress note %s with status %s",
                note_key,
                existing.extraction_status,
            )
            return existing
        if self.resident_resolver is None:
            msg = "A resident ID resolver is required to persist progress notes"
            raise RuntimeError(msg)
        if note.note_date is None:
            msg = f"Progress note {note_key} does not have an effective date"
            raise ValueError(msg)
        resolution = self.resident_resolver(note)
        if resolution is None:
            msg = f"Unable to resolve the resident for progress note {note_key}"
            raise ValueError(msg)
        candidate = ResidentProgressNote(
            resident_id=resolution.resident_id,
            resident_facility_stay_id=resolution.resident_facility_stay_id,
            note_date=note.note_date,
            note_type=note.note_type,
            author=note.author,
            note_text=note.note_text,
            raw_text=note.raw_text,
            note_key=note_key,
            extraction_status=ExtractionStatus.PENDING,
        )
        return self.progress_note_repository.create(candidate)

    def extract_notes(self) -> list[ParsedProgressNote]:
        """Return parsed notes whose configured action sends them to the AI."""
        notes = self._parse_report_notes()
        result = [
            note
            for note in notes
            if self._decide_note_action(note) is ProgressNoteAction.SEND_TO_AI
        ]
        logger.debug(
            "%s of %s progress notes eligible for AI extraction",
            len(result),
            len(notes),
        )
        return result

    def extract_nutrition_notes(self) -> list[ParsedProgressNote]:
        """Parse only notes authored as nutrition or dietetics documentation."""
        notes = self._parse_report_notes()
        result = [
            note
            for note in notes
            if any(
                term in " ".join((note.note_type or "").casefold().split())
                for term in _NUTRITION_ASSESSMENT_TYPE_TERMS
            )
        ]
        logger.debug("%s nutrition notes eligible for import", len(result))
        return result

    def _parse_report_notes(self) -> list[ParsedProgressNote]:
        """Parse every note in the report and validate resident identity."""
        notes = self._split_progress_notes(self._extract_document())
        missing_resident = next(
            (note for note in notes if note.facility_resident_identifier is None),
            None,
        )
        if missing_resident is not None:
            msg = (
                "Unable to determine the resident for a progress note beginning "
                f"on page {missing_resident.page_start} of {self.path.name}"
            )
            raise ValueError(msg)
        return [self._parse_note(note) for note in notes]

    @staticmethod
    def _decide_note_action(note: ParsedProgressNote) -> ProgressNoteAction:
        """Filter configured note types and send unknown types to the AI."""
        note_type = " ".join((note.note_type or "").casefold().split())
        if note_type in _ALWAYS_EXTRACT_NOTE_TYPES:
            return ProgressNoteAction.SEND_TO_AI
        explicitly_filtered = (
            note_type in _NUTRITION_FILTERED_NOTE_TYPES
            or note_type.startswith("nursing")
        )
        if explicitly_filtered:
            if _NUTRITION_TERM_RE.search(note.note_text):
                return ProgressNoteAction.SEND_TO_AI
            return ProgressNoteAction.FILTER
        return ProgressNoteAction.SEND_TO_AI

    def _extract_document(self) -> list[ExtractedNote]:
        extracted_pages: list[ExtractedNote] = []
        facility_resident_identifier: str | None = None
        resident_name: str | None = None
        facility_name: str | None = None
        date_of_birth: date | None = None
        sex: str | None = None
        with pymupdf.open(self.path) as document:
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                lines = self._page_lines(page)
                raw_page_text = page.get_text("text")
                parsed_resident = self._parse_resident(raw_page_text)
                if parsed_resident is not None:
                    facility_resident_identifier, resident_name = parsed_resident
                    date_of_birth = self._parse_date_of_birth(raw_page_text)
                    sex = self._parse_sex(raw_page_text)
                else:
                    date_of_birth = (
                        self._parse_date_of_birth(raw_page_text) or date_of_birth
                    )
                    sex = self._parse_sex(raw_page_text) or sex
                facility_name = (
                    self._parse_facility_name(
                        raw_page_text,
                        "Progress Notes *NEW*",
                    )
                    or facility_name
                )
                body_start = self._body_start_index(lines)
                body_text = "\n".join(
                    str(line["text"]) for line in lines[body_start:]
                ).strip()
                if body_text:
                    extracted_pages.append(
                        ExtractedNote(
                            raw_text=body_text,
                            page_start=page_index + 1,
                            page_end=page_index + 1,
                            facility_resident_identifier=(facility_resident_identifier),
                            resident_name=resident_name,
                            facility_name=facility_name,
                            date_of_birth=date_of_birth,
                            sex=sex,
                        ),
                    )
        return extracted_pages

    @staticmethod
    def _page_lines(page: pymupdf.Page) -> list[dict[str, float | str]]:
        grouped_words: list[list[Word]] = []
        line_tops: list[float] = []
        words = page.get_text("words", sort=True)
        for word in sorted(words, key=lambda item: (item[1], item[0])):
            y0 = float(word[1])
            if line_tops and abs(line_tops[-1] - y0) <= _LINE_Y_TOLERANCE:
                grouped_words[-1].append(word)
            else:
                grouped_words.append([word])
                line_tops.append(y0)

        return [
            {
                "top": min(float(word[1]) for word in line),
                "bottom": max(float(word[3]) for word in line),
                "text": " ".join(
                    str(word[4]) for word in sorted(line, key=lambda item: item[0])
                ),
            }
            for line in grouped_words
        ]

    @staticmethod
    def _body_start_index(lines: list[dict[str, float | str]]) -> int:
        diagnoses_index = next(
            (
                index
                for index, line in enumerate(lines)
                if "diagnoses" in str(line["text"]).casefold()
            ),
            None,
        )
        if diagnoses_index is not None:
            current_bottom = float(lines[diagnoses_index]["bottom"])
            for index in range(diagnoses_index + 1, len(lines)):
                next_top = float(lines[index]["top"])
                if next_top - current_bottom > _HEADER_GAP_THRESHOLD:
                    return index
                current_bottom = float(lines[index]["bottom"])
        return next(
            (
                index
                for index, line in enumerate(lines)
                if _EFFECTIVE_DATE_RE.match(str(line["text"]))
            ),
            len(lines),
        )

    def _parse_note(self, split_note: ExtractedNote) -> ParsedProgressNote:
        """Normalize one extracted note into the declared ProgressNote fields."""
        effective_date = _EFFECTIVE_DATE_RE.search(split_note.raw_text)
        author = _AUTHOR_LINE_RE.search(split_note.raw_text)
        note_type = _NOTE_TYPE_RE.search(split_note.raw_text)
        note_text = _NOTE_TEXT_RE.search(split_note.raw_text)
        parsed_note_text = (
            note_text.group("text").strip()
            if note_text
            else split_note.raw_text.strip()
        )
        return ParsedProgressNote(
            facility_resident_identifier=(split_note.facility_resident_identifier),
            resident_name=split_note.resident_name,
            facility_name=split_note.facility_name,
            date_of_birth=split_note.date_of_birth,
            sex=split_note.sex,
            height_in=split_note.height_in,
            source_page=split_note.page_start,
            note_date=(
                self._date_at_midnight(effective_date.group("date"))
                if effective_date
                else None
            ),
            note_type=note_type.group("type").strip() if note_type else None,
            author=author.group("author").strip() if author else None,
            note_text=clean_note_text(parsed_note_text),
            raw_text=split_note.raw_text,
            source_filename=str(self.path),
        )

    @staticmethod
    def _split_progress_notes(pages: list[ExtractedNote]) -> list[ExtractedNote]:
        notes: list[ExtractedNote] = []
        current_lines: list[str] = []
        facility_resident_identifier: str | None = None
        resident_name: str | None = None
        facility_name: str | None = None
        date_of_birth: date | None = None
        sex: str | None = None
        height_in: float | None = None
        page_start: int | None = None
        page_end: int | None = None

        def append_current_note() -> None:
            nonlocal current_lines, page_start, page_end
            if not current_lines or page_start is None:
                return
            notes.append(
                ExtractedNote(
                    raw_text="\n".join(current_lines).strip(),
                    page_start=page_start,
                    page_end=page_end or page_start,
                    facility_resident_identifier=facility_resident_identifier,
                    resident_name=resident_name,
                    facility_name=facility_name,
                    date_of_birth=date_of_birth,
                    sex=sex,
                    height_in=height_in,
                ),
            )
            current_lines = []
            page_start = None
            page_end = None

        for page in pages:
            if (
                current_lines
                and page.facility_resident_identifier != facility_resident_identifier
                and page.facility_resident_identifier is not None
            ):
                append_current_note()
            for line in page.raw_text.splitlines():
                if _EFFECTIVE_DATE_RE.match(line):
                    append_current_note()
                    current_lines = [line]
                    page_start = page.page_start
                    facility_resident_identifier = page.facility_resident_identifier
                    resident_name = page.resident_name
                    facility_name = page.facility_name
                    date_of_birth = page.date_of_birth
                    sex = page.sex
                    height_in = page.height_in
                elif current_lines:
                    current_lines.append(line)
                if current_lines:
                    page_end = page.page_end
        append_current_note()
        return notes

    @staticmethod
    def _parse_facility_resident_identifier(text: str) -> str | None:
        resident = PccProgressNotesExtractor._parse_resident(text)
        return resident[0] if resident else None

    @staticmethod
    def _parse_resident(text: str) -> tuple[str, str] | None:
        match = _RESIDENT_ID_RE.search(text)
        if match is None:
            return None
        return match.group("id").strip(), match.group("name").strip()

    @staticmethod
    def _parse_date_of_birth(text: str) -> date | None:
        match = _DOB_RE.search(text)
        if match is None:
            return None
        month, day, year = (int(part) for part in match.group("date").split("/"))
        return date(year, month, day)

    @staticmethod
    def _parse_sex(text: str) -> str | None:
        match = _SEX_RE.search(text)
        if match is None:
            return None
        return match.group("sex").casefold()[0]

    @staticmethod
    def _date_at_midnight(value: str) -> datetime:
        month, day, year = (int(part) for part in value.split("/"))
        return datetime(year, month, day, tzinfo=UTC)

    async def _run_data_extraction_agent(
        self,
        extraction_input: ExtractionInput,
    ) -> ExtractedClinicalFacts:
        """Run the agent and enforce its transient-fact result contract."""
        data_extraction_agent = DataExtractionAgent()
        return await data_extraction_agent.run(extraction_input)

    @staticmethod
    def get_note_key(
        facility_resident_identifier: str | None,
        effective_at: datetime | None,
        note_type: str | None,
        author: str | None,
        note_text: str,
    ) -> str:
        """Get unique note key for current progress note."""
        value = "|".join(
            [
                (facility_resident_identifier or "").strip(),
                effective_at.isoformat() if effective_at is not None else "",
                PccProgressNotesExtractor._normalize_text(note_type or ""),
                PccProgressNotesExtractor._normalize_text(author or ""),
                PccProgressNotesExtractor._normalize_text(note_text),
            ],
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_text(value: str) -> str:
        value = unicodedata.normalize("NFKC", value)
        value = re.sub(r"\s+", " ", value)
        return value.strip().lower()
