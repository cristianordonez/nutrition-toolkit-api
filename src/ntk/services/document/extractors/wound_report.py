from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from ntk.models.sql.resident import CsvWoundReportExtraction, SourceReference, Wound

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

    def extract(self, facility_id: str | None = None) -> CsvWoundReportExtraction:
        """Extract wound rows for one resident from a potentially shared report."""
        facility_id, wounds = self._parse_report(
            self._document_text,
            facility_id=facility_id,
        )
        return CsvWoundReportExtraction(
            facility_id=facility_id,
            wounds=wounds,
            source=SourceReference(
                source=str(self.path),
                source_type="WHA Wound Type Tabular Report",
                extracted_at=self._extracted_at(),
            ),
        )

    @classmethod
    def _parse_report(
        cls,
        text: str,
        *,
        facility_id: str | None = None,
    ) -> tuple[str | None, list[Wound]]:
        """Return wound rows matching one resident in the report."""
        header, rows = cls._wound_rows(text)
        if not header:
            return facility_id, []

        selected_id = facility_id.strip() if facility_id else None
        wounds: list[Wound] = []
        for row in rows:
            values = cls._row_values(header, row)
            row_facility_id = cls._optional_value(values, _HEADER_PATIENT_NUMBER)
            if row_facility_id is None:
                continue
            if selected_id is None:
                selected_id = row_facility_id
            if row_facility_id.casefold() != selected_id.casefold():
                continue
            wounds.append(cls._wound_from_values(values))
        return selected_id, wounds

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

    @classmethod
    def _wound_from_values(cls, values: dict[str, str]) -> Wound:
        return Wound(
            type=cls._optional_value(values, "Wound Type") or "Unknown",
            location=cls._optional_value(values, "Wound Location") or "Unknown",
            weeks_in_treatment=WoundReportExtractor._parse_int(
                values.get("Weeks In Treatment"),
            ),
            progress=cls._optional_value(values, "Wound Progress"),
            stage=cls._optional_value(values, "Stage"),
            size=cls._optional_value(values, "Size (LxWxD) cm"),
            assessment_note=cls._optional_value(values, "Assessment Note"),
            physician_orders=cls._optional_value(values, "Physician Orders"),
            physician_orders_notes=cls._optional_value(
                values,
                "Physician Orders Notes",
            ),
        )

    @staticmethod
    def _optional_value(values: dict[str, str], column: str) -> str | None:
        return values.get(column, "").strip() or None

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
