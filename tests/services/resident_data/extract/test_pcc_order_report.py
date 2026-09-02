from __future__ import annotations

import asyncio
import typing

import pymupdf

from ntk.models.extracted_fact_create import OrderPayload
from ntk.services.resident_data.extract.pcc_order_report import (
    OrderReportMode,
    PccOrderReportExtractor,
)

if typing.TYPE_CHECKING:
    import pathlib


def test_order_extractor_retains_page_and_does_not_parse_diagnosis_as_resident(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "orders.pdf"
    with pymupdf.open() as document:
        pages = (
            (
                "Lab order related to ESSENTIAL PRIMARY\n"
                "HYPERTENSION (I10)\n"
                "Laboratory\nActive\n06/16/2026\n06/16/2026\nN"
            ),
            "Renal diet\nDietary - Diet\nActive\n08/01/2026\nN",
        )
        for page_number, order_text in enumerate(pages, start=1):
            page = document.new_page(width=700, height=500)
            lines = [
                "Order Listing Report",
                "Embassy Manor at Edison",
                "Resident: Ortiz, Carmen (210757) Order Status: Active",
                "Ortiz, Carmen (210757)",
                *order_text.splitlines(),
                f"Page {page_number} of 2",
            ]
            for line_number, line in enumerate(lines, start=1):
                page.insert_text((20, line_number * 20), line, fontsize=8)
        document.save(path)

    facts = asyncio.run(PccOrderReportExtractor(path).extract())
    extractor = PccOrderReportExtractor(path)

    assert [fact.facility_resident_identifier for fact in facts] == [
        "210757",
        "210757",
    ]
    assert [fact.source_page for fact in facts] == [1, 2]
    assert isinstance(facts[0].payload, OrderPayload)
    assert facts[0].payload.summary.endswith("HYPERTENSION (I10)")
    assert extractor.report_mode is OrderReportMode.ACTIVE_SNAPSHOT


def test_order_extractor_deduplicates_repeated_order_blocks(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "duplicate-orders.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=700, height=500)
        lines = [
            "Order Listing Report",
            "Facility",
            "Resident: Resident, Example (RES1) Order Status: Active",
            "Resident, Example (RES1)",
            "Renal diet",
            "Dietary - Diet",
            "Active",
            "08/01/2026",
            "N",
            "Resident, Example (RES1)",
            "Renal diet",
            "Dietary - Diet",
            "Active",
            "08/01/2026",
            "N",
        ]
        for line_number, line in enumerate(lines, start=1):
            page.insert_text((20, line_number * 20), line, fontsize=8)
        document.save(path)

    facts = asyncio.run(PccOrderReportExtractor(path).extract())

    assert len(facts) == 1
    assert facts[0].facility_resident_identifier == "RES1"
