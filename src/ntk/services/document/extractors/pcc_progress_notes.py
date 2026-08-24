from __future__ import annotations

import logging
import re
import typing
from datetime import UTC, datetime

import pdfplumber
from pydantic import BaseModel

from ntk.models.resident_data import ProgressNote, SourceReference

from .base import BaseExtractor
from .registry import register_extractor

logger = logging.getLogger(__name__)

logging.getLogger("pdfminer").setLevel(logging.WARNING)

if typing.TYPE_CHECKING:
    from pdfplumber.page import Page


class ExtractedNote(BaseModel):
    raw_text: str
    page_start: int | None
    page_end: int | None


class ExtractedPage(BaseModel):
    text: str
    page_number: int
    header_bottom: float


@register_extractor
class PccProgressNotesExtractor(BaseExtractor):
    """Recognize and chunk a PCC progress notes report."""

    def is_expected_format(self) -> bool:
        """Return whether the document is a PCC progress notes report."""
        return self._first_page_contains("Progress Notes *NEW*")

    def create_chunks(self) -> list[ProgressNote]:
        """Create assessment chunks from the progress notes report."""
        pages = self._extract_pages()
        notes = self._split_progress_notes(pages)
        logger.debug(
            "%s notes extracted from progress report. Normalizing contents.",
            len(notes),
        )
        return [self._parse_note(note) for note in notes]

    def extract(self) -> list[ProgressNote]:
        """Extract structured progress notes from the report."""
        return self.create_chunks()

    def _parse_note(self, split_note: ExtractedNote) -> ProgressNote:
        """Normalize one extracted note into structured resident data."""
        effective_date_match = re.search(
            r"^Effective Date[ \t]*:[ \t]*(\d{1,2}/\d{1,2}/\d{4})",
            split_note.raw_text,
            flags=re.MULTILINE,
        )
        author_match = re.search(
            r"Author[ \t]*:[ \t]*(.*?)(?=\[)",
            split_note.raw_text,
            flags=re.DOTALL,
        )
        note_type = re.search(
            r"Type\s*:\s*(.+)$",
            split_note.raw_text,
            flags=re.MULTILINE,
        )
        note_text_match = re.search(
            r"^Note Text\s*:\s*(.*)",
            split_note.raw_text,
            flags=re.MULTILINE | re.DOTALL,
        )
        return ProgressNote(
            note_date=(
                datetime.strptime(
                    effective_date_match.group(1).strip(),
                    "%m/%d/%Y",
                ).replace(tzinfo=UTC)
                if effective_date_match
                else None
            ),
            note_type=note_type.group(1).strip() if note_type else None,
            author=(" ".join(author_match.group(1).split()) if author_match else None),
            note_text=(
                note_text_match.group(1).strip()
                if note_text_match
                else split_note.raw_text.strip()
            ),
            raw_text=split_note.raw_text,
            source=SourceReference(
                source_name=self.path.name,
                source_type="PCC Progress Notes *NEW* Report",
                page_start=split_note.page_start,
                page_end=split_note.page_end,
                extracted_at=datetime.now(tz=UTC),
            ),
        )

    def _extract_pages(self) -> list[ExtractedPage]:
        """Extract report pages with the repeated PCC header removed."""
        pages = []
        with pdfplumber.open(self.path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                header_bottom = self._find_header_bottom(page)
                if header_bottom is None:
                    continue
                cropped = page.crop(
                    (
                        0,
                        header_bottom,
                        page.width,
                        page.height,
                    ),
                )
                pages.append(
                    ExtractedPage(
                        page_number=page_number,
                        header_bottom=header_bottom,
                        text=(cropped.extract_text() or "").strip(),
                    ),
                )
        return pages

    def _find_header_bottom(
        self,
        page: Page,
        gap_threshold: float = 10,
    ) -> float | None:
        lines = self._get_lines(page)
        diagnoses_index = next(
            (i for i, line in enumerate(lines) if "Diagnoses :" in line["text"]),
            None,
        )
        if diagnoses_index is None:
            return None
        current = lines[diagnoses_index]
        for next_line in lines[diagnoses_index + 1 :]:
            gap = next_line["top"] - current["bottom"]
            if gap > gap_threshold:
                # First line after the repeated header
                return next_line["top"]
            current = next_line
        return current["bottom"]

    @staticmethod
    def _get_lines(page: Page) -> list[dict]:
        words = page.extract_words()
        lines: dict[float, list[dict]] = {}
        for word in words:
            top = round(word["top"], 1)
            lines.setdefault(top, []).append(word)
        results = []
        for top in sorted(lines):
            line_words = sorted(
                lines[top],
                key=lambda word: word["x0"],
            )
            results.append(
                {
                    "top": min(word["top"] for word in line_words),
                    "bottom": max(word["bottom"] for word in line_words),
                    "text": " ".join(word["text"] for word in line_words),
                },
            )
        return results

    @staticmethod
    def _split_progress_notes(
        pages: list[ExtractedPage],
    ) -> list[ExtractedNote]:
        """Split extracted page text at each effective-date marker."""
        notes: list[ExtractedNote] = []
        current_lines: list[str] = []
        page_start: int | None = None
        page_end: int | None = None
        for page in pages:
            page_number = page.page_number
            text = page.text
            lines = text.splitlines()
            for line in lines:
                is_new_note = re.match(
                    r"^Effective Date[ \t]*:",
                    line,
                )
                if is_new_note:
                    # Finish previous note
                    if current_lines and page_start is not None:
                        notes.append(
                            ExtractedNote(
                                raw_text="\n".join(current_lines).strip(),
                                page_start=page_start,
                                page_end=page_end or page_start,
                            ),
                        )
                    current_lines = [line]
                    page_start = page_number
                    page_end = page_number
                elif current_lines:
                    current_lines.append(line)
                    page_end = page_number
        if current_lines and page_start is not None:
            notes.append(
                ExtractedNote(
                    raw_text="\n".join(current_lines).strip(),
                    page_start=page_start,
                    page_end=page_end or page_start,
                ),
            )
        return notes
