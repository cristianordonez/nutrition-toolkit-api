from __future__ import annotations

import re
import typing
from datetime import UTC, date, datetime

import pdfplumber

from ntk.models.resident_data import SourceReference, WeightVitalsExtraction
from ntk.models.sql.resident import WeightHistoryEntry

from .base import BaseExtractor
from .registry import register_extractor

if typing.TYPE_CHECKING:
    from pdfplumber.page import Page


_WEIGHT_LINE_RE = re.compile(
    r"^(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"\d{1,2}:\d{2}\s+"
    r"(?P<weight>\d+(?:\.\d+)?)\s+"
    r"Lbs\s*"
    r"(?:\((?P<description>[^)]*)\))?",
)
_FACILITY_ID_RE = re.compile(r"Resident\s*:.+?\((?P<facility_id>[A-Z]{0,4}\d+)\)")
_HEIGHT_RE = re.compile(r"\bHeight\s*:\s*(?P<height>\d+(?:\.\d+)?)\s+Inches\b")
_DOB_RE = re.compile(
    r"\b(?:DOB|Date of Birth)\s*:\s*(?P<dob>\d{1,2}/\d{1,2}/\d{4})\b",
    flags=re.IGNORECASE,
)


@register_extractor
class PccWeightHistoryExtractor(BaseExtractor):
    """Recognize a PCC weight history report."""

    def is_expected_format(self) -> bool:
        """Return whether the document is a PCC weight history report."""
        return self._first_page_contains("Weights and Vitals Summary")

    def extract(self) -> WeightVitalsExtraction:
        """Extract available data from a PCC weights-and-vitals report."""
        document_text = self._document_text
        weight_history = [
            entry
            for page_text in self._extract_pages()
            for entry in self._parse_weight_summary(page_text)
        ]
        date_of_birth = self._parse_date_of_birth(document_text)
        return WeightVitalsExtraction(
            source=SourceReference(
                source_name=self.path.name,
                source_type="PCC Weights and Vitals Summary",
                page_start=1,
                page_end=None,
                extracted_at=datetime.now(tz=UTC),
            ),
            facility_id=self._parse_facility_id(document_text),
            height=self._parse_height(document_text),
            date_of_birth=date_of_birth.isoformat() if date_of_birth else None,
            age=self._calculate_age(date_of_birth),
            weight_history=weight_history,
        )

    def _extract_pages(self) -> list[str]:
        """Extract report pages with the repeated PCC header removed."""
        pages = []
        with pdfplumber.open(self.path) as pdf:
            for page in pdf.pages:
                header_bottom = self._find_header_bottom(page)
                if header_bottom is None:
                    text = page.extract_text() or ""
                else:
                    cropped = page.crop(
                        (
                            0,
                            header_bottom,
                            page.width,
                            page.height,
                        ),
                    )
                    text = cropped.extract_text() or ""
                pages.append(text.strip())
        return pages

    def _find_header_bottom(
        self,
        page: Page,
        gap_threshold: float = 10,
    ) -> float | None:
        lines = self._get_lines(page)
        warnings_index = next(
            (
                i
                for i, line in enumerate(lines)
                if "Date Value Warnings" in line["text"]
            ),
            None,
        )
        if warnings_index is None:
            return None
        current = lines[warnings_index]
        for next_line in lines[warnings_index + 1 :]:
            gap = next_line["top"] - current["bottom"]
            if gap > gap_threshold:
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

    @classmethod
    def _parse_weight_summary(cls, text: str) -> list[WeightHistoryEntry]:
        _, _, weight_summary = text.partition("Weight Summary")
        if not weight_summary:
            return []
        return [
            entry
            for line in weight_summary.splitlines()
            if (entry := cls._parse_weight_line(line)) is not None
        ]

    @staticmethod
    def _parse_weight_line(line: str) -> WeightHistoryEntry | None:
        match = _WEIGHT_LINE_RE.match(line.strip())
        if match is None:
            return None
        month, day, year = (int(part) for part in match.group("date").split("/"))
        weight_date = date(year, month, day)
        description = match.group("description")
        return WeightHistoryEntry(
            date=weight_date.isoformat(),
            weight_lb=float(match.group("weight")),
            description=description.strip() if description else None,
        )

    @staticmethod
    def _parse_facility_id(text: str) -> str | None:
        match = _FACILITY_ID_RE.search(text)
        return match.group("facility_id") if match else None

    @staticmethod
    def _parse_height(text: str) -> float | None:
        match = _HEIGHT_RE.search(text)
        return float(match.group("height")) if match else None

    @staticmethod
    def _parse_date_of_birth(text: str) -> date | None:
        match = _DOB_RE.search(text)
        if match is None:
            return None
        month, day, year = (int(part) for part in match.group("dob").split("/"))
        return date(year, month, day)

    @staticmethod
    def _calculate_age(date_of_birth: date | None) -> int | None:
        if date_of_birth is None:
            return None
        return datetime.now(tz=UTC).year - date_of_birth.year
