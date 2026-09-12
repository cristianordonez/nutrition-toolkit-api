from __future__ import annotations

import asyncio
import typing
from datetime import UTC, datetime

import pymupdf

from ntk.models.extracted_fact_create import ExtractedFactCreate, LabPayload
from ntk.pipelines.person.ingestion.extract.pcc_lab_results import (
    LabReportSplitter,
    PccLabResultsExtractor,
)

if typing.TYPE_CHECKING:
    import pathlib


def _lab_payloads(facts: list[ExtractedFactCreate]) -> list[LabPayload]:
    payloads = [fact.payload for fact in facts if isinstance(fact.payload, LabPayload)]
    assert len(payloads) == len(facts)
    return payloads


def _insert_header(  # noqa: PLR0913
    page: pymupdf.Page,
    *,
    person: str,
    identifier: str,
    collection_date: str,
    source_key: str,
    order_number: str = "1",
    page_number: str = "Page 1 of 1",
) -> None:
    for index, value in enumerate(
        (
            "Lab Results Report",
            f"Resident: {person} ({identifier})",
            f"Collection Date: {collection_date}",
            f"Order #: {order_number}",
            f"Source Key: {source_key}",
            "Laboratory: ACULABS",
            page_number,
        ),
    ):
        page.insert_text((20, 30 + (index * 14)), value, fontsize=8)


def _insert_results(
    page: pymupdf.Page,
    rows: list[tuple[str, str, str, str, str, str]],
    *,
    top: int = 145,
) -> None:
    for x_position, heading in zip(
        (20, 180, 250, 320, 390, 460),
        ("Test", "Result", "Unit", "Ref.", "Flag", "Status"),
        strict=True,
    ):
        page.insert_text((x_position, top), heading, fontsize=8)
    for row_index, row in enumerate(rows, start=1):
        for x_position, value in zip(
            (20, 180, 250, 320, 390, 460),
            row,
            strict=True,
        ):
            if value:
                page.insert_text(
                    (x_position, top + (row_index * 18)),
                    value,
                    fontsize=8,
                )


def test_lab_extractor_includes_collection_time_in_observed_at(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "labs-with-time.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=700, height=500)
        page.insert_text((20, 40), "Lab Results Report", fontsize=8)
        page.insert_text((20, 60), "Resident: Example (RES1)", fontsize=8)
        page.insert_text(
            (20, 80),
            "Collection Date: 07/29/2026 15:55",
            fontsize=8,
        )
        for point, value in (
            ((180, 110), "Result"),
            ((250, 110), "Unit"),
            ((320, 110), "Ref."),
            ((390, 110), "Flag"),
            ((460, 110), "Status"),
            ((20, 130), "ALBUMIN"),
            ((180, 130), "3.0"),
            ((250, 130), "g/dL"),
            ((320, 130), "3.5-5.0"),
            ((390, 130), "L"),
            ((460, 130), "Final"),
        ):
            page.insert_text(point, value, fontsize=8)
        document.save(path)

    facts = asyncio.run(PccLabResultsExtractor(path).extract())
    payloads = _lab_payloads(facts)

    assert len(facts) == 1
    assert facts[0].source_person_identifier == "RES1"
    assert facts[0].source_page == 1
    assert payloads[0].observed_at == datetime(
        2026,
        7,
        29,
        15,
        55,
        tzinfo=UTC,
    )


def test_name_alert_person_header_is_not_replaced_by_lab_phone_number(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "name-alert-labs.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=700, height=500)
        lines = (
            "Lab Results Report",
            "Laboratory: ACULABS - ORDERS",
            "Resident: Patel, Maniben(NAME ALERT)",
            "(210486)",
            "Collection Date:08/20/2026 12:49",
            "Order #:250022721",
            "Source Key:e4e0ef9dd15677a2",
            (
                "Performing Laboratory Information: ACULABS INC "
                "EAST BRUNSWICK NJ (732)777-2588"
            ),
            "Page 1 of 1",
        )
        for line_number, line in enumerate(lines, start=1):
            page.insert_text((20, line_number * 18), line, fontsize=8)
        _insert_results(
            page,
            [("FREE T4", "1.1", "ng/dL", "0.9-1.7", "", "Final")],
            top=200,
        )
        document.save(path)

    with pymupdf.open(path) as document:
        reports = LabReportSplitter.split(document)
    facts = asyncio.run(PccLabResultsExtractor(path).extract())

    assert len(reports) == 1
    assert reports[0].source_person_identifier == "210486"
    assert reports[0].source_person_name == "Patel, Maniben"
    assert {fact.source_person_identifier for fact in facts} == {"210486"}


def test_one_person_multi_page_report_inherits_report_metadata(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "multi-page-labs.pdf"
    with pymupdf.open() as document:
        first_page = document.new_page(width=700, height=500)
        _insert_header(
            first_page,
            person="Example Person",
            identifier="RES1",
            collection_date="07/29/2026 15:55",
            source_key="SOURCE-1",
            page_number="Page 1 of 2",
        )
        _insert_results(
            first_page,
            [("ALBUMIN", "3.0", "g/dL", "3.5-5.0", "L", "Final")],
        )
        second_page = document.new_page(width=700, height=500)
        second_page.insert_text((20, 30), "Order # 1", fontsize=8)
        second_page.insert_text((20, 45), "SourceKey: SOURCE-1", fontsize=8)
        second_page.insert_text((20, 60), "Page 2 of 2", fontsize=8)
        _insert_results(
            second_page,
            [("GLUCOSE", "92", "mg/dL", "70-100", "", "Final")],
            top=100,
        )
        document.save(path)

    facts = asyncio.run(PccLabResultsExtractor(path).extract())
    payloads = _lab_payloads(facts)

    assert [fact.source_person_identifier for fact in facts] == ["RES1", "RES1"]
    assert [fact.source_page for fact in facts] == [1, 2]
    assert [payload.name for payload in payloads] == ["ALBUMIN", "GLUCOSE"]
    assert payloads[1].observed_at == datetime(
        2026,
        7,
        29,
        15,
        55,
        tzinfo=UTC,
    )


def test_same_person_can_have_multiple_reports_with_missing_or_zero_orders(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "multiple-reports.pdf"
    with pymupdf.open() as document:
        for collection_date, source_key, order_number, lab_name in (
            ("07/29/2026 15:55", "SOURCE-1", "", "ALBUMIN"),
            ("08/03/2026 09:15", "SOURCE-2", "0", "GLUCOSE"),
        ):
            page = document.new_page(width=700, height=500)
            _insert_header(
                page,
                person="Example Person",
                identifier="RES1",
                collection_date=collection_date,
                source_key=source_key,
                order_number=order_number,
            )
            _insert_results(
                page,
                [(lab_name, "3.0", "g/dL", "", "", "Final")],
            )
        document.save(path)

    with pymupdf.open(path) as document:
        reports = LabReportSplitter.split(document)
    facts = asyncio.run(PccLabResultsExtractor(path).extract())
    payloads = _lab_payloads(facts)

    assert len(reports) == 2  # noqa: PLR2004
    assert [report.source_key for report in reports] == ["SOURCE-1", "SOURCE-2"]
    assert [report.order_number for report in reports] == [None, None]
    assert [fact.source_person_identifier for fact in facts] == ["RES1", "RES1"]
    assert payloads[0].observed_at != payloads[1].observed_at


def test_multiple_persons_transition_from_last_page_to_new_page_one(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "all-persons-labs.pdf"
    with pymupdf.open() as document:
        first_page = document.new_page(width=700, height=500)
        _insert_header(
            first_page,
            person="Agarwal, Kiran",
            identifier="EN140387",
            collection_date="07/29/2026",
            source_key="AGARWAL-1",
            page_number="Page 1 of 2",
        )
        _insert_results(
            first_page,
            [("ALBUMIN", "3.0", "g/dL", "", "", "Final")],
        )
        continuation = document.new_page(width=700, height=500)
        continuation.insert_text((20, 30), "Order #: 1", fontsize=8)
        continuation.insert_text((20, 45), "SourceKey: AGARWAL-1", fontsize=8)
        continuation.insert_text((20, 60), "Page 2 of 2", fontsize=8)
        _insert_results(
            continuation,
            [("GLUCOSE", "92", "mg/dL", "", "", "Final")],
            top=100,
        )
        next_report = document.new_page(width=700, height=500)
        _insert_header(
            next_report,
            person="ANDERSON, BARBARA H",
            identifier="190372",
            collection_date="08/01/2026",
            source_key="ANDERSON-1",
            page_number="Page 1 of 1",
        )
        _insert_results(
            next_report,
            [("SODIUM", "140", "mmol/L", "", "", "Final")],
        )
        document.save(path)

    facts = asyncio.run(PccLabResultsExtractor(path).extract())

    assert [fact.source_person_identifier for fact in facts] == [
        "EN140387",
        "EN140387",
        "190372",
    ]
    assert [fact.source_page for fact in facts] == [1, 2, 3]


def test_pending_invalid_and_redraw_rows_are_not_extracted(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "non-final-labs.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=700, height=500)
        _insert_header(
            page,
            person="Example Person",
            identifier="RES1",
            collection_date="08/01/2026",
            source_key="SOURCE-1",
        )
        _insert_results(
            page,
            [
                ("PENDING TEST", "Pending", "", "", "", "Preliminary"),
                ("INVALID TEST", "Invalid", "", "", "", "Final"),
                ("REDRAW NOTE", "1", "", "", "", "Final"),
                ("ALBUMIN", "3.2", "g/dL", "", "L", "Final"),
            ],
        )
        document.save(path)

    facts = asyncio.run(PccLabResultsExtractor(path).extract())
    payloads = _lab_payloads(facts)

    assert [payload.name for payload in payloads] == ["ALBUMIN"]


def test_demo_extracts_lab_results_without_identity(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "deidentified-labs.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=700, height=500)
        _insert_header(
            page,
            person="",
            identifier="",
            collection_date="08/25/2026 08:49",
            source_key="DEMO-SOURCE",
        )
        _insert_results(
            page,
            [("ALBUMIN", "3.2", "g/dL", "3.5-5.0", "L", "Final")],
        )
        document.save(path)

    extractor = PccLabResultsExtractor(path)

    assert asyncio.run(extractor.extract()) == []
    facts = asyncio.run(extractor.extract_for_demo())

    assert len(facts) == 1
    assert facts[0].source_person_identifier is None
    assert facts[0].source_person_name is None
    assert isinstance(facts[0].payload, LabPayload)
    assert facts[0].payload.name == "ALBUMIN"
