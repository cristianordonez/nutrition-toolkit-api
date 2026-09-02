from __future__ import annotations

import csv
import functools
import io
import re
from datetime import UTC, datetime

from ntk.models.extracted_fact_create import ExtractedFactCreate, WoundPayload

from .base import BaseExtractor
from .registry import register_extractor

_WOUND_REPORT_MARKERS = (
    "CUSTOM Wound Type Tabular Report - WHA",
    "Wound Healing Associates",
    "Wound Report",
    "Wound Evaluation",
)
_HEADER_PATIENT_NUMBER = "Patient Number"
_CSV_SUFFIX = ".csv"
_REPORT_DATE_RE = re.compile(
    r"\b(?P<start>\d{1,2}/\d{1,2}/\d{4})"
    r"(?:\s*-\s*(?P<end>\d{1,2}/\d{1,2}/\d{4}))?\b",
)
_FACILITY_RE = re.compile(r"(?m)^Facility:\s*(?P<name>[^,\r\n]+)")
_EMBASSY_MANOR_NAME = "Embassy Manor at Edison"

ResidentWound = tuple[str, str | None, WoundPayload]
WoundIdentity = tuple[str, str | None, datetime | None]
_FREE_TEXT_FIELDS = (
    "assessment_note",
    "physician_orders",
    "physician_orders_notes",
)


@register_extractor
class WoundReportExtractor(BaseExtractor):
    """Recognize a wound report."""

    def is_expected_format(self) -> bool:
        """Return whether the document is a wound report."""
        if self._is_pdf(self.path):
            return self._first_page_contains(*_WOUND_REPORT_MARKERS)
        if self.path.suffix.lower() != _CSV_SUFFIX:
            return False
        return any(marker in self._csv_text for marker in _WOUND_REPORT_MARKERS)

    async def extract(
        self,
        facility_id: str | None = None,
    ) -> list[ExtractedFactCreate]:
        """Extract each wound row as a transient fact."""
        report_text = self._document_text if self._is_pdf(self.path) else self._csv_text
        facility_name = self._parse_wound_facility_name(report_text)
        parsed_wounds = self._parse_report(
            report_text,
            facility_id=facility_id,
        )
        return [
            self._build_extracted_fact(
                wound,
                facility_resident_identifier=facility_resident_identifier,
                resident_name=resident_name,
                facility_name=facility_name,
            )
            for facility_resident_identifier, resident_name, wound in parsed_wounds
        ]

    def _extract_report(
        self,
        facility_id: str | None = None,
    ) -> list[ResidentWound]:
        """Extract each wound with the resident identifier on its row."""
        if not self.is_expected_format():
            msg = f"Attempted to read unsupported wound report: {self.path}"
            raise TypeError(msg)
        report_text = self._document_text if self._is_pdf(self.path) else self._csv_text
        return self._parse_report(
            report_text,
            facility_id=facility_id,
        )

    @functools.cached_property
    def _csv_text(self) -> str:
        """Read CSV text explicitly without passing it to the PDF reader."""
        return self.path.read_text(encoding="utf-8-sig", errors="replace")

    @classmethod
    def _parse_report(
        cls,
        text: str,
        *,
        facility_id: str | None = None,
    ) -> list[ResidentWound]:
        """Return all wound rows, optionally limited to one resident."""
        header, rows = cls._wound_rows(text)
        if not header:
            return []

        selected_id = facility_id.strip() if facility_id else None
        observed_at = cls._parse_report_date(text)
        wounds: dict[WoundIdentity, ResidentWound] = {}
        for row in rows:
            values = cls._row_values(header, row)
            facility_resident_identifier = cls._optional_value(
                values,
                _HEADER_PATIENT_NUMBER,
            )
            if facility_resident_identifier is None:
                continue
            if (
                selected_id is not None
                and facility_resident_identifier.casefold() != selected_id.casefold()
            ):
                continue
            wound = cls._wound_from_values(values, observed_at=observed_at)
            identity = (
                facility_resident_identifier.casefold(),
                wound.wound_number.casefold() if wound.wound_number else None,
                observed_at,
            )
            existing = wounds.get(identity)
            if existing is None:
                wounds[identity] = (
                    facility_resident_identifier,
                    cls._optional_value(values, "Name"),
                    wound,
                )
                continue
            wounds[identity] = (
                existing[0],
                existing[1] or cls._optional_value(values, "Name"),
                cls._merge_wounds(existing[2], wound),
            )
        return list(wounds.values())

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
    def _wound_from_values(
        cls,
        values: dict[str, str],
        *,
        observed_at: datetime | None = None,
    ) -> WoundPayload:
        return WoundPayload(
            wound_number=cls._optional_value(values, "Wnd #"),
            wound_type=cls._optional_value(values, "Wound Type") or "Unknown",
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
            observed_at=observed_at,
        )

    @staticmethod
    def _parse_report_date(text: str) -> datetime | None:
        """Return the report range's end date as a UTC observation timestamp."""
        report_header = text.partition(_HEADER_PATIENT_NUMBER)[0]
        match = _REPORT_DATE_RE.search(report_header)
        if match is None:
            return None
        value = match.group("end") or match.group("start")
        try:
            month, day, year = (int(part) for part in value.split("/"))
            return datetime(year, month, day, tzinfo=UTC)
        except ValueError:
            return None

    @staticmethod
    def _parse_wound_facility_name(text: str) -> str | None:
        match = _FACILITY_RE.search(text)
        if match is None:
            return None
        facility_name = match.group("name").strip()
        if "embassy manor" in facility_name.casefold():
            return _EMBASSY_MANOR_NAME
        return facility_name

    @staticmethod
    def _optional_value(values: dict[str, str], column: str) -> str | None:
        value = values.get(column, "").strip()
        if not value or value.casefold() in {"nan", "none", "null"}:
            return None
        return value

    @classmethod
    def _merge_wounds(
        cls,
        existing: WoundPayload,
        incoming: WoundPayload,
    ) -> WoundPayload:
        """Merge duplicate rows without losing more complete wound details."""
        merged = existing.model_copy(deep=True)
        for field_name in WoundPayload.model_fields:
            if field_name == "type":
                continue
            current = getattr(merged, field_name)
            new_value = getattr(incoming, field_name)
            if field_name in _FREE_TEXT_FIELDS:
                setattr(
                    merged,
                    field_name,
                    cls._merge_text(current, new_value),
                )
            elif current is None and new_value is not None:
                setattr(merged, field_name, new_value)
        return merged

    @staticmethod
    def _merge_text(existing: str | None, incoming: str | None) -> str | None:
        if existing is None:
            return incoming
        if incoming is None:
            return existing
        normalized_existing = " ".join(existing.split()).casefold()
        normalized_incoming = " ".join(incoming.split()).casefold()
        if normalized_existing == normalized_incoming:
            return existing
        if normalized_existing in normalized_incoming:
            return incoming
        if normalized_incoming in normalized_existing:
            return existing
        return f"{existing}\n{incoming}"

    @staticmethod
    def _parse_int(value: str | None) -> int | None:
        if value is None or not value.strip():
            return None
        try:
            return int(value)
        except ValueError:
            return None
