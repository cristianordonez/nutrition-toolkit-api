from __future__ import annotations

import re
from datetime import UTC, date, datetime

from ntk.models.sql.resident import (
    PccOrder,
    PccOrderReportExtraction,
    SourceReference,
)

from .base import BaseExtractor
from .registry import register_extractor

_CATEGORY_RE = re.compile(
    r"\s*(?P<category>Dietary\s*-\s*Diet|Dietary\s*-\s*Supplements|Dietary\s*-|"
    r"Enteral Feed|Pharmacy|Other|Laboratory|Diagnostic)\s+"
    r"(?P<status>Active|Inactive|Discontinued|Completed)\s+"
    r"(?P<revision_date>\d{2}/\d{2}/\d{4})"
    r"(?:\s+(?P<supply_last_order_date>\d{2}/\d{2}/\d{4}))?"
    r"(?:\s+(?P<supply_reorder>[YN]))?",
)
_RESIDENT_RE = re.compile(
    r"^Resident\s*:\s*(?P<name>.+?)\s*\((?P<id>[A-Z]{0,4}\d+)\)",
)


@register_extractor
class PccOrderReportExtractor(BaseExtractor):
    """Recognize and extract a PCC order listing report."""

    def is_expected_format(self) -> bool:
        """Return whether the document is a PCC order listing report."""
        return self._first_page_contains("Order Listing Report")

    def extract(self) -> PccOrderReportExtraction:
        """Extract the resident and order rows from a PCC order report."""
        document_text = self._document_text
        resident_name, facility_id = self._parse_resident(document_text)
        return PccOrderReportExtraction(
            facility_id=facility_id,
            orders=self._parse_orders(document_text, resident_name, facility_id),
            source=SourceReference(
                source=str(self.path),
                source_type="PCC Order Listing Report",
                extracted_at=datetime.now(tz=UTC),
            ),
        )

    @staticmethod
    def _parse_resident(text: str) -> tuple[str | None, str | None]:
        for line in text.splitlines():
            if match := _RESIDENT_RE.match(line.strip()):
                return match.group("name").strip(), match.group("id").strip()
        return None, None

    @classmethod
    def _parse_orders(
        cls,
        text: str,
        resident_name: str | None,
        facility_id: str | None,
    ) -> list[PccOrder]:
        """Parse rows without depending on report-header coordinates."""
        if resident_name is None or facility_id is None:
            return []

        resident_marker = f"{resident_name} ({facility_id})"
        orders: list[PccOrder] = []
        row_lines: list[str] = []

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or cls._is_report_chrome(line):
                continue
            if line.startswith(resident_marker):
                cls._append_order(orders, row_lines)
                row_lines = [line.removeprefix(resident_marker).strip()]
            elif row_lines:
                row_lines.append(line)

        cls._append_order(orders, row_lines)
        return orders

    @classmethod
    def _append_order(cls, orders: list[PccOrder], row_lines: list[str]) -> None:
        if order := cls._parse_order_text(" ".join(row_lines)):
            orders.append(order)

    @staticmethod
    def _parse_order_text(order_text: str) -> PccOrder | None:
        match = _CATEGORY_RE.search(order_text)
        if match is None:
            return None

        category = " ".join(match.group("category").split())
        summary_parts = [order_text[: match.start()].strip()]
        trailing_text = order_text[match.end() :].strip()
        if category == "Dietary -" and trailing_text.endswith("Supplements"):
            category = "Dietary - Supplements"
            trailing_text = trailing_text.removesuffix("Supplements").strip()
        if trailing_text:
            summary_parts.append(trailing_text)

        return PccOrder(
            summary=" ".join(part for part in summary_parts if part),
            category=category,
            status=match.group("status"),
            revision_date=PccOrderReportExtractor._parse_date(
                match.group("revision_date"),
            ),
            supply_last_order_date=PccOrderReportExtractor._parse_date(
                match.group("supply_last_order_date"),
            ),
            supply_reorder=match.group("supply_reorder"),
        )

    @staticmethod
    def _is_report_chrome(line: str) -> bool:
        return (
            line.startswith(
                (
                    "Order Listing Report",
                    "Facility #:",
                    "Date:",
                    "Time:",
                    "Resident:",
                    "Resident :",
                    "Resident Order",
                    "Page ",
                ),
            )
            or line == "Name Summary Category Status Date Last Order Date Reorder"
        )

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if value is None:
            return None
        month, day, year = (int(part) for part in value.split("/"))
        return date(year, month, day)
