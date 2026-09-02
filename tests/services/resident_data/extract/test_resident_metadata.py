from __future__ import annotations

import asyncio
import typing
from datetime import date

import pymupdf

from ntk.services.resident_data.extract.base import BaseExtractor
from ntk.services.resident_data.extract.pcc_lab_results import (
    PccLabResultsExtractor,
)
from ntk.services.resident_data.extract.pcc_order_report import (
    PccOrderReportExtractor,
)
from ntk.services.resident_data.extract.pcc_progress_notes import (
    PccProgressNotesExtractor,
)
from ntk.services.resident_data.extract.pcc_weight_history import (
    PccWeightHistoryExtractor,
)

if typing.TYPE_CHECKING:
    import pathlib


def test_facility_name_can_appear_before_or_after_report_title() -> None:
    assert (
        BaseExtractor._parse_facility_name(  # noqa: SLF001
            "Weights and Vitals Summary\nEmbassy Manor at Edison\nTime: 07:51",
            "Weights and Vitals Summary",
        )
        == "Embassy Manor at Edison"
    )
    assert (
        BaseExtractor._parse_facility_name(  # noqa: SLF001
            "Embassy Manor at Edison\nLab Results Report\nLaboratory: ACULABS",
            "Lab Results Report",
        )
        == "Embassy Manor at Edison"
    )


def test_pcc_resident_headers_return_identifier_and_name() -> None:
    text = "Resident: Zheng, Jing (120046)"
    assert PccWeightHistoryExtractor._parse_resident(text) == (  # noqa: SLF001
        "120046",
        "Zheng, Jing",
    )
    assert PccLabResultsExtractor._parse_resident(text) == (  # noqa: SLF001
        "120046",
        "Zheng, Jing",
    )
    assert PccProgressNotesExtractor._parse_resident(text) == (  # noqa: SLF001
        "120046",
        "Zheng, Jing",
    )


def test_deterministic_extractors_populate_resident_demographics(
    tmp_path: pathlib.Path,
) -> None:
    expected_height = 64.5
    weights_path = tmp_path / "weights.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=700, height=500)
        page.insert_text((20, 40), "Weights and Vitals Summary", fontsize=8)
        page.insert_text((20, 60), "Facility", fontsize=8)
        page.insert_text((20, 80), "Resident: Example (RES1)", fontsize=8)
        page.insert_text((20, 100), "Height: 64.5 Inches", fontsize=8)
        page.insert_text((20, 120), "08/01/2026 09:30 130 Lbs", fontsize=8)
        document.save(weights_path)

    labs_path = tmp_path / "labs.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=700, height=500)
        page.insert_text((20, 40), "Lab Results Report", fontsize=8)
        page.insert_text((20, 60), "Resident: Example (RES1)", fontsize=8)
        page.insert_text((20, 80), "DOB: 02/01/1946", fontsize=8)
        page.insert_text((20, 100), "Collection Date: 08/01/2026", fontsize=8)
        for point, value in (
            ((180, 130), "Result"),
            ((250, 130), "Unit"),
            ((320, 130), "Ref."),
            ((390, 130), "Flag"),
            ((460, 130), "Status"),
            ((20, 150), "ALBUMIN"),
            ((180, 150), "3.0"),
            ((250, 150), "g/dL"),
            ((320, 150), "3.5-5.0"),
            ((390, 150), "L"),
            ((460, 150), "Final"),
        ):
            page.insert_text(point, value, fontsize=8)
        document.save(labs_path)

    weight_fact = asyncio.run(PccWeightHistoryExtractor(weights_path).extract())[0]
    lab_fact = asyncio.run(PccLabResultsExtractor(labs_path).extract())[0]

    assert weight_fact.height_in == expected_height
    assert lab_fact.date_of_birth == date(1946, 2, 1)
    assert PccProgressNotesExtractor._parse_sex("Gender: Female") == "f"  # noqa: SLF001
    assert PccProgressNotesExtractor._parse_date_of_birth(  # noqa: SLF001
        "DOB: 02/01/1946",
    ) == date(1946, 2, 1)


def test_order_rows_return_resident_name_and_identifier() -> None:
    orders = PccOrderReportExtractor._parse_orders(  # noqa: SLF001
        "Piros, Stephen (EN140514) Renal diet Dietary - Diet Active 08/27/2026",
    )

    assert len(orders) == 1
    facility_resident_identifier, resident_name, order = orders[0]
    assert facility_resident_identifier == "EN140514"
    assert resident_name == "Piros, Stephen"
    assert order.summary == "Renal diet"


def test_order_rows_do_not_treat_diagnosis_codes_as_residents() -> None:
    orders = PccOrderReportExtractor._parse_orders(  # noqa: SLF001
        "Ortiz, Carmen (210757) Lab order related to ESSENTIAL PRIMARY\n"
        "HYPERTENSION (I10)\n"
        "Laboratory\n"
        "Active\n"
        "06/16/2026\n"
        "06/16/2026\n"
        "N",
    )

    assert len(orders) == 1
    facility_resident_identifier, _, order = orders[0]
    assert facility_resident_identifier == "210757"
    assert order.summary == "Lab order related to ESSENTIAL PRIMARY HYPERTENSION (I10)"
