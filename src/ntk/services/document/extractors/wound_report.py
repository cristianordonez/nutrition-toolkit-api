from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from ntk.models.resident_data import (
    ResidentWoundData,
    SourceReference,
    WoundReportExtraction,
)
from ntk.models.sql.resident import WoundData

from .base import BaseExtractor
from .registry import register_extractor

_WOUND_REPORT_MARKERS = (
    "CUSTOM Wound Type Tabular Report - WHA",
    "Wound Healing Associates",
    "Wound Report",
    "Wound Evaluation",
)
_HEADER_PATIENT_NUMBER = "Patient Number"


@register_extractor
class WoundReportExtractor(BaseExtractor):
    """Recognize a wound report."""

    def is_expected_format(self) -> bool:
        """Return whether the document is a wound report."""
        if self._is_pdf(self.path):
            return self._first_page_contains(*_WOUND_REPORT_MARKERS)
        text = self._document_text
        return any(marker in text for marker in _WOUND_REPORT_MARKERS)

    def extract(self) -> WoundReportExtraction:
        """Extract wound rows grouped by resident."""
        residents = self._parse_residents(self._document_text)
        return WoundReportExtraction(
            source=SourceReference(
                source_name=self.path.name,
                source_type="WHA Wound Type Tabular Report",
                page_start=None,
                page_end=None,
                extracted_at=self._extracted_at(),
            ),
            residents=residents,
        )

    @classmethod
    def _parse_residents(cls, text: str) -> list[ResidentWoundData]:
        header, rows = cls._wound_rows(text)
        if not header:
            return []
        residents_by_id: dict[str, ResidentWoundData] = {}
        for row in rows:
            values = cls._row_values(header, row)
            facility_id = values.get("Patient Number", "").strip()
            if not facility_id:
                continue
            wound = cls._wound_from_values(values)
            resident = residents_by_id.setdefault(
                facility_id,
                ResidentWoundData(
                    facility_id=facility_id,
                    resident_name=values.get("Name", "").strip() or None,
                ),
            )
            resident.wounds.append(wound)
        return list(residents_by_id.values())

    @staticmethod
    def _wound_rows(text: str) -> tuple[list[str], list[list[str]]]:
        rows = list(csv.reader(io.StringIO(text)))
        for index, row in enumerate(rows):
            stripped = [value.strip() for value in row]
            if stripped and stripped[0] == _HEADER_PATIENT_NUMBER:
                return stripped, rows[index + 1 :]
        return [], []

    @staticmethod
    def _row_values(header: list[str], row: list[str]) -> dict[str, str]:
        normalized_row = [value.strip() for value in row]
        return {
            column: normalized_row[index] if index < len(normalized_row) else ""
            for index, column in enumerate(header)
        }

    @staticmethod
    def _wound_from_values(values: dict[str, str]) -> WoundData:
        return WoundData(
            type=values.get("Wound Type", "").strip() or "Unknown",
            location=values.get("Wound Location", "").strip() or "Unknown",
            weeks_in_treatment=WoundReportExtractor._parse_int(
                values.get("Weeks In Treatment"),
            ),
            stage=values.get("Stage", "").strip() or None,
            progress=values.get("Wound Progress", "").strip() or None,
        )

    @staticmethod
    def _parse_int(value: str | None) -> int | None:
        if value is None or not value.strip():
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _extracted_at() -> datetime:
        return datetime.now(tz=UTC)
