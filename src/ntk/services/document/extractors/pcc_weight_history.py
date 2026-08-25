from __future__ import annotations

import re
from datetime import UTC, date, datetime

import pymupdf

from ntk.models.sql.resident import (
    PccWeightVitalsExtraction,
    SourceReference,
    WeightHistoryEntry,
)

from .base import BaseExtractor
from .registry import register_extractor

_WEIGHT_LINE_RE = re.compile(
    r"^(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<time>\d{1,2}:\d{2})\s+"
    r"(?P<weight>\d+(?:\.\d+)?)\s+"
    r"Lbs\s*"
    r"(?:\((?P<description>[^)]*)\))?",
    flags=re.IGNORECASE | re.MULTILINE,
)
_FACILITY_ID_RE = re.compile(r"Resident\s*:.+?\((?P<id>[A-Z]{0,4}\d+)\)")
_HEIGHT_RE = re.compile(
    r"\bHeight\s*:\s*(?P<height>\d+(?:\.\d+)?)\s+Inches\b",
    flags=re.IGNORECASE,
)
_ADMISSION_DATE_RE = re.compile(
    r"\b(?:DOA|(?:Admit|Admission) Date)\s*:\s*"
    r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\b",
    flags=re.IGNORECASE,
)

WeightKey = tuple[str, str, float, str | None]


@register_extractor
class PccWeightHistoryExtractor(BaseExtractor):
    """Recognize and extract a PCC weight history report."""

    def is_expected_format(self) -> bool:
        """Return whether the document is a PCC weight history report."""
        return self._first_page_contains("Weights and Vitals Summary")

    def extract(self) -> PccWeightVitalsExtraction:
        """Extract only fields declared by PccWeightVitalsExtraction."""
        document_text, weight_history = self._extract_pdf()
        return PccWeightVitalsExtraction(
            admission_date=self._parse_admission_date(document_text),
            height=self._parse_height(document_text),
            facility_id=self._parse_facility_id(document_text),
            weight_history=weight_history,
            source=SourceReference(
                source=str(self.path),
                source_type="PCC Weights and Vitals Summary",
                extracted_at=datetime.now(tz=UTC),
            ),
        )

    def _extract_pdf(self) -> tuple[str, list[WeightHistoryEntry]]:
        page_texts: list[str] = []
        entries: list[WeightHistoryEntry] = []
        seen: set[WeightKey] = set()
        with pymupdf.open(self.path) as document:
            for page_number in range(document.page_count):
                page = document.load_page(page_number)
                page_text = page.get_text("text")
                page_texts.append(page_text)
                for key, entry in self._parse_weight_rows(page_text):
                    if key not in seen:
                        seen.add(key)
                        entries.append(entry)
        return "\n".join(page_texts), entries

    @classmethod
    def _parse_weight_summary(cls, text: str) -> list[WeightHistoryEntry]:
        """Parse dated pound measurements while ignoring other vital rows."""
        return [entry for _, entry in cls._parse_weight_rows(text)]

    @staticmethod
    def _parse_weight_rows(text: str) -> list[tuple[WeightKey, WeightHistoryEntry]]:
        rows: list[tuple[WeightKey, WeightHistoryEntry]] = []
        for match in _WEIGHT_LINE_RE.finditer(text):
            month, day, year = (int(part) for part in match.group("date").split("/"))
            weight_date = date(year, month, day).isoformat()
            weight = float(match.group("weight"))
            raw_description = match.group("description")
            description = raw_description.strip() if raw_description else None
            entry = WeightHistoryEntry(
                date=weight_date,
                weight_lb=weight,
                description=description,
            )
            key = (weight_date, match.group("time"), weight, description)
            rows.append((key, entry))
        return rows

    @staticmethod
    def _parse_facility_id(text: str) -> str | None:
        match = _FACILITY_ID_RE.search(text)
        return match.group("id") if match else None

    @staticmethod
    def _parse_height(text: str) -> float | None:
        match = _HEIGHT_RE.search(text)
        return float(match.group("height")) if match else None

    @staticmethod
    def _parse_admission_date(text: str) -> date | None:
        match = _ADMISSION_DATE_RE.search(text)
        if match is None:
            return None
        month, day, year = (int(part) for part in match.group("date").split("/"))
        return date(year, month, day)
