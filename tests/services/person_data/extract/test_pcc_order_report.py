from __future__ import annotations

import asyncio
import typing
from datetime import UTC, datetime

import pymupdf

from ntk.models.extracted_fact_create import (
    DietPayload,
    EnteralFeedingPayload,
    FluidPlanPayload,
    MedicationPayload,
    MiscOrderPayload,
    SupplementPayload,
)
from ntk.models.sql.clinical import FeedingMethod
from ntk.pipelines.person.ingestion.extract.pcc_order_report import (
    OrderReportMode,
    PccOrderReportExtractor,
)

if typing.TYPE_CHECKING:
    import pathlib


def test_order_extractor_retains_page_and_does_not_parse_diagnosis_as_person(
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
                "Date: 09/01/2026",
                "Time: 4:00 PM",
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

    assert [fact.source_person_identifier for fact in facts] == [
        "210757",
        "210757",
    ]
    assert [fact.source_page for fact in facts] == [1, 2]
    assert isinstance(facts[0].payload, MiscOrderPayload)
    assert facts[0].payload.description.endswith("HYPERTENSION (I10)")
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
            "Date: 09/01/2026",
            "Time: 4:00 PM",
            "Resident: Person, Example (RES1) Order Status: Active",
            "Person, Example (RES1)",
            "Renal diet",
            "Dietary - Diet",
            "Active",
            "08/01/2026",
            "N",
            "Person, Example (RES1)",
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
    assert facts[0].source_person_identifier == "RES1"


def test_order_extractor_parses_text_date_seconds_and_eastern_time(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "text-date-orders.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=700, height=500)
        lines = [
            "Order Listing Report",
            "Embassy Manor at Edison",
            "Date: Aug 27, 2026",
            "Time: 10:35:23 ET",
            "Resident: Dickow, Denise (210407) Order Status: Active",
        ]
        for line_number, line in enumerate(lines, start=1):
            page.insert_text((20, line_number * 20), line, fontsize=8)
        document.save(path)

    observed_at = PccOrderReportExtractor(path).source_observed_at

    assert observed_at == datetime(2026, 8, 27, 14, 35, 23, tzinfo=UTC)


def test_order_extractor_routes_supported_order_domains() -> None:
    observed_at = datetime(2026, 8, 27, 14, 35, 23, tzinfo=UTC)
    text = """
    Order Listing Report
    Dickow, Denise (210407)
    Glucerna PO 8 OZ two times a day for malnutrition
    Dietary -
    Supplements
    Active
    08/05/2026
    N
    Dickow, Denise (210407)
    Acetaminophen Tablet 325 MG Give 2 tablets by mouth every 6 hours as needed
    Pharmacy
    Active
    03/24/2026
    N
    Dickow, Denise (210407)
    Regular diet Mechanical Soft texture, Thin consistency
    Dietary - Diet
    Active
    03/26/2026
    N
    Dickow, Denise (210407)
    Weekly skin assessment
    Other
    Active
    03/24/2026
    N
    Dickow, Denise (210407)
    Fluid restriction 1500 mL per day
    Other
    Active
    03/24/2026
    N
    """

    orders = PccOrderReportExtractor._parse_orders(  # noqa: SLF001
        text,
        report_observed_at=observed_at,
    )
    payloads = [order for _, _, order in orders]

    assert len(payloads) == 5  # noqa: PLR2004
    assert isinstance(payloads[0], SupplementPayload)
    assert payloads[0].amount == 8  # noqa: PLR2004
    assert payloads[0].unit == "oz"
    assert payloads[0].frequency == "BID"
    assert payloads[0].route == "PO"
    assert isinstance(payloads[1], MedicationPayload)
    assert payloads[1].frequency == "Q6H PRN"
    assert isinstance(payloads[2], DietPayload)
    assert payloads[2].diet_type == "regular"
    assert payloads[2].texture == "mechanical_soft"
    assert isinstance(payloads[3], MiscOrderPayload)
    assert payloads[3].description == "Weekly skin assessment"
    assert isinstance(payloads[4], FluidPlanPayload)
    assert payloads[4].restriction_ml_day == 1500  # noqa: PLR2004


def test_order_extractor_recognizes_hyphenated_enteral_category() -> None:
    observed_at = datetime(2026, 9, 9, 16, 15, 57, tzinfo=UTC)
    text = """
    Order Listing Report
    Mao, Chongsen (EN140493)
    Enteral Feed Order one time a day Provide Nepro 1.8 @ 65 ml/hr via peg up at
    4:00 pm and down until TV of 1100ml infused providing 1947 kcal, 89 g protein
    Enteral - Feed
    Active
    08/25/2026
    N
    """

    orders = PccOrderReportExtractor._parse_orders(  # noqa: SLF001
        text,
        report_observed_at=observed_at,
    )

    assert len(orders) == 1
    identifier, name, payload = orders[0]
    assert identifier == "EN140493"
    assert name == "Mao, Chongsen"
    assert isinstance(payload, EnteralFeedingPayload)
    assert payload.formula == "Nepro 1.8"
    assert payload.feeding_method is FeedingMethod.CYCLIC


def test_demo_extracts_orders_when_identity_column_was_removed(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "deidentified-orders.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=700, height=700)
        lines = [
            "Order Listing Report",
            "Date: Aug 27, 2026",
            "Time: 07:52:42 ET",
            "Resident:",
            "Order Status: Active",
            "Resident",
            "Name",
            "Order",
            "Summary",
            "Order",
            "Category",
            "Order",
            "Status",
            "Revision",
            "Date",
            "Supply",
            "Reorder",
            "NAS, CCD diet Regular texture, Thin consistency",
            "Dietary - Diet",
            "Active",
            "07/31/2026",
            "N",
            "Aspirin Tablet 81 MG Give 1 tablet by mouth daily",
            "Pharmacy",
            "Active",
            "02/16/2026",
            "N",
        ]
        for line_number, line in enumerate(lines, start=1):
            page.insert_text((20, line_number * 20), line, fontsize=8)
        document.save(path)

    extractor = PccOrderReportExtractor(path)

    assert asyncio.run(extractor.extract()) == []
    facts = asyncio.run(extractor.extract_for_demo())

    assert len(facts) == 2  # noqa: PLR2004
    assert all(fact.source_person_identifier is None for fact in facts)
    assert isinstance(facts[0].payload, DietPayload)
    assert isinstance(facts[1].payload, MedicationPayload)
