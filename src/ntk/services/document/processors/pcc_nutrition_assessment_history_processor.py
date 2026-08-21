from __future__ import annotations

import re
import typing
from bisect import bisect_right
from datetime import datetime

from ntk.models.document import ChunkType, DocumentType

from .base import IngestionProcessor

_UPPERCASE_DIAGNOSIS_RATIO = 0.75

if typing.TYPE_CHECKING:
    from ntk.models.document import Document, DocumentChunk


class PccNutritionAssessmentHistoryProcessor(IngestionProcessor):
    """Select nutrition assessments from a PointClickCare Progress Report."""

    document_type = DocumentType.PCC_PROGRESS_REPORT
    chunk_type = ChunkType.ASSESSMENT

    def create_chunks(self, document: Document) -> list[DocumentChunk]:
        """Create one clean chunk for each possibly multi-page progress note."""
        page_starts: list[int] = []
        parts: list[str] = []
        offset = 0
        for raw_page_text in self.page_texts:
            page_text = self._clean_page(raw_page_text)
            page_starts.append(offset)
            parts.append(page_text)
            offset += len(page_text) + 1
        text = "\n".join(parts)
        note_matches = list(re.finditer(r"(?im)^\s*Note\s+Text\s*:\s*", text))
        chunks: list[DocumentChunk] = []
        for assessment_index, note_match in enumerate(note_matches):
            next_start = (
                note_matches[assessment_index + 1].start()
                if assessment_index + 1 < len(note_matches)
                else len(text)
            )
            content = text[note_match.start() : next_start]
            author = re.search(r"(?im)^\s*Author\s*:", content)
            if author:
                content = content[: author.start()]
            header_start = (
                note_matches[assessment_index - 1].end() if assessment_index else 0
            )
            headers = list(
                re.finditer(
                    r"(?im)Effective\s+Date\s*:\s*"
                    r"(?P<date>\d{2}/\d{2}/\d{4})(?:\s+\S+)?\s+"
                    r"Type\s*:\s*(?P<type>[^\r\n]+)",
                    text[header_start : note_match.start()],
                ),
            )
            header = headers[-1] if headers else None
            header_offset = (
                header_start + header.start() if header else note_match.start()
            )
            content_end = note_match.start() + len(content)
            assessment_date = (
                datetime.strptime(  # noqa: DTZ007
                    header.group("date"),
                    "%m/%d/%Y",
                ).date()
                if header
                else None
            )
            chunks.extend(
                self._create_chunk(
                    document,
                    len(chunks),
                    content,
                    {
                        "note_type": header.group("type").strip() if header else None,
                        "page": bisect_right(page_starts, header_offset),
                        "page_start": bisect_right(page_starts, header_offset),
                        "page_end": bisect_right(page_starts, max(content_end - 1, 0)),
                        "assessment_index": assessment_index,
                        "assessment_date": assessment_date,
                    },
                ),
            )
        return chunks

    @classmethod
    def _clean_page(cls, text: str) -> str:
        """Remove the repeated PCC resident header and page-number footer."""
        lines = text.splitlines()
        diagnoses_index = next(
            (
                index
                for index, line in enumerate(lines)
                if re.match(r"\s*Diagnoses\s*:", line, re.IGNORECASE)
            ),
            None,
        )
        if diagnoses_index is not None:
            content_index = diagnoses_index + 1
            while content_index < len(lines):
                line = lines[content_index].strip()
                if cls._is_content_start(line) or not cls._looks_like_diagnosis(line):
                    break
                content_index += 1
            lines = lines[content_index:]

        return "\n".join(
            line
            for line in lines
            if not re.fullmatch(r"\s*Page\s+\d+\s+of\s+\d+\s*", line, re.IGNORECASE)
        ).strip()

    @staticmethod
    def _is_content_start(line: str) -> bool:
        """Recognize common first lines after a repeated PCC page header."""
        return bool(
            re.match(
                r"(?:Effective\s+Date\s*:|Note\s+Text\s*:|LATE\s+ENTRY\b|"
                r"Weight\s*:|Height\s*:|IBW\b|BMI\s*:|SUMMARY\b|Goals\s*:|"
                r"Recommendations\s*:)",
                line,
                re.IGNORECASE,
            ),
        )

    @staticmethod
    def _looks_like_diagnosis(line: str) -> bool:
        """Identify wrapped uppercase diagnosis text following the header label."""
        letters = [character for character in line if character.isalpha()]
        if not letters:
            return True
        uppercase = sum(character.isupper() for character in letters)
        return uppercase / len(letters) >= _UPPERCASE_DIAGNOSIS_RATIO
