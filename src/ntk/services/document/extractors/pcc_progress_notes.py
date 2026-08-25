from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime

import pymupdf
from pydantic import BaseModel

from ntk.models.sql.resident import (
    PccProgressNotesExtraction,
    ProgressNote,
    SourceReference,
)

from .base import BaseExtractor
from .registry import register_extractor

logger = logging.getLogger(__name__)

_FACILITY_ID_RE = re.compile(r"\bResident\s*:[^(]+?\((?P<id>[A-Z]{0,4}\d+)\)")
_ADMISSION_DATE_RE = re.compile(
    r"\b(?:Admission|Admit|Readmission) Date\s*:\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})",
    flags=re.IGNORECASE,
)
_DOB_RE = re.compile(
    r"\b(?:DOB|Date of Birth)\s*:\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})",
    flags=re.IGNORECASE,
)
_GENDER_RE = re.compile(
    r"\b(?:Gender|Sex)\s*:\s*(?P<gender>Female|Male|F|M)\b",
    flags=re.IGNORECASE,
)
_ALLERGIES_RE = re.compile(
    r"\bAllerg(?:y|ies)\s*:\s*(?P<value>.+?)(?=\s+(?:Diagnoses|Diagnosis|"
    r"Admission|Admit|Readmission|Gender|Sex|DOB|Date of Birth)\s*:|$)",
    flags=re.IGNORECASE | re.DOTALL,
)
_DIAGNOSES_RE = re.compile(
    r"\bDiagnos(?:e|es)\s*:\s*(?P<value>.+?)(?=\s+(?:Allerg(?:y|ies)|Admission|"
    r"Admit|Readmission|Gender|Sex|DOB|Date of Birth|Effective Date)\s*:|$)",
    flags=re.IGNORECASE | re.DOTALL,
)
_EFFECTIVE_DATE_RE = re.compile(
    r"^Effective Date\s*:\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})",
    flags=re.IGNORECASE,
)
_LINE_Y_TOLERANCE = 2.0
_HEADER_GAP_THRESHOLD = 10.0

Word = tuple[float, float, float, float, str, int, int, int]


class ExtractedNote(BaseModel):
    raw_text: str
    page_start: int
    page_end: int


class ExtractedPage(BaseModel):
    text: str
    page_number: int


@register_extractor
class PccProgressNotesExtractor(BaseExtractor):
    """Recognize and extract a PCC progress-notes report."""

    def is_expected_format(self) -> bool:
        """Return whether the document is a PCC progress-notes report."""
        return self._first_page_contains("Progress Notes *NEW*")

    def extract(self) -> PccProgressNotesExtraction:
        """Return only fields declared by PccProgressNotesExtraction."""
        document_text, pages = self._extract_document()
        date_of_birth = self._parse_date(document_text, _DOB_RE)
        return PccProgressNotesExtraction(
            facility_id=self._parse_facility_id(document_text),
            gender=self._parse_gender(document_text),
            admission_date=self._parse_report_date(document_text),
            age=self._calculate_age(date_of_birth),
            allergies=self._parse_allergies(document_text),
            diagnoses=self._parse_diagnoses(document_text),
            progress_notes=[
                self._parse_note(note) for note in self._split_progress_notes(pages)
            ],
            source=self._source_reference(),
        )

    def _extract_document(self) -> tuple[str, list[ExtractedPage]]:
        if not self._is_pdf(self.path):
            text = self._document_text
            return text, [ExtractedPage(text=text, page_number=1)]
        page_texts: list[str] = []
        extracted_pages: list[ExtractedPage] = []
        with pymupdf.open(self.path) as document:
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                lines = self._page_lines(page)
                page_texts.append("\n".join(str(line["text"]) for line in lines))
                body_start = self._body_start_index(lines)
                body_text = "\n".join(
                    str(line["text"]) for line in lines[body_start:]
                ).strip()
                if body_text:
                    extracted_pages.append(
                        ExtractedPage(text=body_text, page_number=page_index + 1),
                    )
        return "\n".join(page_texts), extracted_pages

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

    def _parse_note(self, split_note: ExtractedNote) -> ProgressNote:
        """Normalize one extracted note into the declared ProgressNote fields."""
        effective_date = _EFFECTIVE_DATE_RE.search(split_note.raw_text)
        author = re.search(
            r"^Author\s*:\s*(?P<author>.*?)(?:\s*\[.*)?$",
            split_note.raw_text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        note_type = re.search(
            r"Type:\s*(?P<type>.+)$",
            split_note.raw_text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        note_text = re.search(
            r"^Note Text\s*:\s*(?P<text>.*)",
            split_note.raw_text,
            flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        return ProgressNote(
            note_date=(
                self._date_at_midnight(effective_date.group("date"))
                if effective_date
                else None
            ),
            note_type=note_type.group("type").strip() if note_type else None,
            author=author.group("author").strip() if author else None,
            note_text=(
                note_text.group("text").strip()
                if note_text
                else split_note.raw_text.strip()
            ),
            source=self._source_reference(),
            raw_text=split_note.raw_text,
        )

    @staticmethod
    def _split_progress_notes(pages: list[ExtractedPage]) -> list[ExtractedNote]:
        notes: list[ExtractedNote] = []
        current_lines: list[str] = []
        page_start: int | None = None
        page_end: int | None = None
        for page in pages:
            for line in page.text.splitlines():
                if _EFFECTIVE_DATE_RE.match(line):
                    if current_lines and page_start is not None:
                        notes.append(
                            ExtractedNote(
                                raw_text="\n".join(current_lines).strip(),
                                page_start=page_start,
                                page_end=page_end or page_start,
                            ),
                        )
                    current_lines = [line]
                    page_start = page.page_number
                elif current_lines:
                    current_lines.append(line)
                if current_lines:
                    page_end = page.page_number
        if current_lines and page_start is not None:
            notes.append(
                ExtractedNote(
                    raw_text="\n".join(current_lines).strip(),
                    page_start=page_start,
                    page_end=page_end or page_start,
                ),
            )
        logger.debug("%s notes extracted from progress report", len(notes))
        return notes

    def _source_reference(self) -> SourceReference:
        return SourceReference(
            source=str(self.path),
            source_type="PCC Progress Notes *NEW* Report",
            extracted_at=datetime.now(tz=UTC),
        )

    @staticmethod
    def _parse_facility_id(text: str) -> str | None:
        match = _FACILITY_ID_RE.search(text)
        return match.group("id") if match else None

    @staticmethod
    def _parse_report_date(text: str) -> str | None:
        parsed_date = PccProgressNotesExtractor._parse_date(text, _ADMISSION_DATE_RE)
        return parsed_date.isoformat() if parsed_date else None

    @staticmethod
    def _parse_gender(text: str) -> str | None:
        match = _GENDER_RE.search(text)
        if match is None:
            return None
        gender = match.group("gender").casefold()
        if gender == "f":
            return "Female"
        if gender == "m":
            return "Male"
        return gender.title()

    @staticmethod
    def _parse_date(text: str, pattern: re.Pattern[str]) -> date | None:
        match = pattern.search(text)
        if match is None:
            return None
        month, day, year = (int(part) for part in match.group("date").split("/"))
        return date(year, month, day)

    @staticmethod
    def _date_at_midnight(value: str) -> datetime:
        month, day, year = (int(part) for part in value.split("/"))
        return datetime(year, month, day, tzinfo=UTC)

    @staticmethod
    def _calculate_age(date_of_birth: date | None) -> int | None:
        if date_of_birth is None:
            return None
        today = datetime.now(tz=UTC).date()
        return (
            today.year
            - date_of_birth.year
            - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
        )

    @staticmethod
    def _parse_list_field(text: str, pattern: re.Pattern[str]) -> list[str]:
        match = pattern.search(" ".join(text.split()))
        if match is None:
            return []
        value = match.group("value").strip()
        if not value or value.casefold() in {
            "nka",
            "nkda",
            "none",
            "no known allergies",
        }:
            return []
        return [
            item.strip(" .;:")
            for item in re.split(r"\s*[;,]\s*|\s{2,}", value)
            if item.strip(" .;:")
        ]

    @classmethod
    def _parse_allergies(cls, text: str) -> list[str]:
        return cls._parse_list_field(text, _ALLERGIES_RE)

    @classmethod
    def _parse_diagnoses(cls, text: str) -> list[str]:
        return cls._parse_list_field(text, _DIAGNOSES_RE)
