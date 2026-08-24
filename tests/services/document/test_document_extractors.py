from __future__ import annotations

import inspect
import typing
from datetime import date, datetime

import pytest

from ntk.services.document.document_extractor_service import load_extractors
from ntk.services.document.extractors.base import BaseExtractor
from ntk.services.document.extractors.pcc_lab_results import PccLabResultsExtractor
from ntk.services.document.extractors.pcc_order_report import PccOrderReportExtractor
from ntk.services.document.extractors.pcc_weight_history import (
    PccWeightHistoryExtractor,
)
from ntk.services.document.extractors.registry import (
    EXTRACTOR_REGISTRY,
    register_extractor,
)
from ntk.services.document.extractors.wound_report import WoundReportExtractor

if typing.TYPE_CHECKING:
    import pathlib

EXTRACTED_HEIGHT = 72.0
EXTRACTED_AGE = 80
EXPECTED_ORDER_COUNT = 4
EXPECTED_MEDICATION_COUNT = 1


def test_base_extractor_is_abstract(tmp_path: pathlib.Path) -> None:
    with pytest.raises(TypeError):
        BaseExtractor(tmp_path)

    assert BaseExtractor.__abstractmethods__ == {"is_expected_format"}


def test_subclass_is_registered_only_when_decorated() -> None:
    class ExplicitExtractor(BaseExtractor):
        def is_expected_format(self) -> bool:
            return True

    assert "ExplicitExtractor" not in EXTRACTOR_REGISTRY

    try:
        assert register_extractor(ExplicitExtractor) is ExplicitExtractor
        assert EXTRACTOR_REGISTRY["ExplicitExtractor"] is ExplicitExtractor
    finally:
        EXTRACTOR_REGISTRY.pop("ExplicitExtractor", None)


def test_service_registers_only_concrete_extractors() -> None:
    extractor_types = load_extractors()

    assert [extractor_type.__name__ for extractor_type in extractor_types] == [
        "PccWeightHistoryExtractor",
        "PccProgressNotesExtractor",
        "PccLabResultsExtractor",
        "WoundReportExtractor",
        "PccOrderReportExtractor",
        "NutritionCareManualExtractor",
        "DietManualExtractor",
        "MiscExtractor",
    ]
    assert "KnowledgeExtractor" not in EXTRACTOR_REGISTRY
    assert all(
        not inspect.isabstract(extractor_type) for extractor_type in extractor_types
    )


@pytest.mark.parametrize(
    ("extractor_name", "first_page_text"),
    [
        ("PccWeightHistoryExtractor", "Weights and Vitals Summary"),
        ("PccProgressNotesExtractor", "Progress Notes *NEW*"),
        ("PccLabResultsExtractor", "Laboratory Results"),
        ("WoundReportExtractor", "Wound Evaluation"),
        ("PccOrderReportExtractor", "Order Listing Report"),
        ("NutritionCareManualExtractor", "Nutrition Care Manual"),
        ("DietManualExtractor", "Diet Manual"),
    ],
)
def test_format_methods_use_cached_first_page_text(
    tmp_path: pathlib.Path,
    extractor_name: str,
    first_page_text: str,
) -> None:
    extractor_types = {
        extractor_type.__name__: extractor_type for extractor_type in load_extractors()
    }
    extractor = extractor_types[extractor_name](tmp_path / "document.pdf")
    extractor.__dict__["_first_page_text"] = first_page_text

    assert extractor.is_expected_format() is True


def test_misc_extractor_is_unconditional_fallback(tmp_path: pathlib.Path) -> None:
    extractor_types = {
        extractor_type.__name__: extractor_type for extractor_type in load_extractors()
    }
    extractor = extractor_types["MiscExtractor"](tmp_path / "unknown.txt")

    assert extractor.is_expected_format() is True


def test_first_page_text_closes_pdf_and_is_cached(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    class Page:
        @staticmethod
        def extract_text() -> str:
            return "Progress Notes *NEW*"

    class Pdf:
        def __init__(self) -> None:
            self.pages = [Page()]

        def __enter__(self) -> typing.Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def open_pdf(_path: pathlib.Path) -> Pdf:
        nonlocal calls
        calls += 1
        return Pdf()

    monkeypatch.setattr(
        "ntk.services.document.extractors.base.pdfplumber.open",
        open_pdf,
    )
    extractor_type = next(
        item
        for item in load_extractors()
        if item.__name__ == "PccProgressNotesExtractor"
    )
    extractor = extractor_type(tmp_path / "progress-notes.pdf")

    assert extractor.is_expected_format() is True
    assert extractor.is_expected_format() is True
    assert calls == 1


def test_weight_history_extractor_parses_weight_summary_rows(
    tmp_path: pathlib.Path,
) -> None:
    extractor = PccWeightHistoryExtractor(tmp_path / "weights.pdf")

    entries = extractor._parse_weight_summary(  # noqa: SLF001
        """Height Summary
08/03/2026 19:45 67 Inches (Lying down)
Weight Summary
08/16/2026 09:19 332 Lbs (Mechanical Lift)
08/05/2026 07:19 332.2 Lbs (Wheelchair)
Only vitals with data are displayed Page 1 of 1""",
    )

    assert [entry.model_dump() for entry in entries] == [
        {
            "date": "2026-08-16",
            "weight_lb": 332.0,
            "description": "Mechanical Lift",
        },
        {
            "date": "2026-08-05",
            "weight_lb": 332.2,
            "description": "Wheelchair",
        },
    ]


def test_weight_history_extractor_parses_vitals_metadata(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = PccWeightHistoryExtractor(tmp_path / "weights.pdf")
    monkeypatch.setattr(
        "ntk.services.document.extractors.pcc_weight_history.datetime",
        type(
            "FrozenDateTime",
            (),
            {
                "now": staticmethod(lambda tz=None: datetime(2026, 8, 23, tzinfo=tz)),
            },
        ),
    )
    text = (
        "Resident: Orosz, Joseph (EN140316) Vital: BMI Percentile, Height, Weight\n"
        "Orosz, Joseph (EN140316) Location: 2B 288 P, "
        f"Height: {EXTRACTED_HEIGHT:g} Inches, "
        "DOB: 02/01/1946"
    )

    assert extractor._parse_facility_id(text) == "EN140316"  # noqa: SLF001
    assert extractor._parse_height(text) == EXTRACTED_HEIGHT  # noqa: SLF001
    assert (
        extractor._calculate_age(  # noqa: SLF001
            extractor._parse_date_of_birth(text),  # noqa: SLF001
        )
        == EXTRACTED_AGE
    )


def test_lab_results_extractor_parses_latest_completed_results(
    tmp_path: pathlib.Path,
) -> None:
    extractor = PccLabResultsExtractor(tmp_path / "labs.pdf")
    pages = [
        (
            "Lab Results Report\n"
            "Resident:MCMEEN, ROBERT (EN140227) "
            "Collection Date:06/16/2026 10:36 Status:Completed\n"
            "Result Unit Ref. Range Flag Status\n"
            "ALBUMIN 3.6 g/dL 3.5-5.2 Final"
        ),
        (
            "Lab Results Report\n"
            "Resident:MCMEEN, ROBERT (EN140227) "
            "Collection Date:07/28/2026 08:32 Status:Completed\n"
            "Result Unit Ref. Range Flag Status\n"
            "SEDIMENTATION RATE 24 mm/h <20 H Final\n"
            "ALBUMIN 3.5 g/dL 3.5-5.2 Final\n"
            "C REACT.PROTEIN INFLAMM. 24 mg/L < 8.0 H Final\n"
            "UNABLE TO OBTAIN * Final"
        ),
        (
            "Lab Results Report\n"
            "MCMEEN, ROBERT (EN140227) Order #:249607917 "
            "SourceKey:646d1e9f2754a558\n"
            "Source Id:560263 10103122 Result Unit Ref. Range Flag Status\n"
            "eGFR 99 See note >59 Final\n"
            "ALBUMIN 3.5 g/dL 3.5-5.2 Final"
        ),
    ]

    results = extractor._parse_lab_results(pages)  # noqa: SLF001
    latest_date = extractor._latest_labs_date(results)  # noqa: SLF001
    latest_results = [result for result in results if result.date == "2026-07-28"]

    assert extractor._parse_facility_id("\n".join(pages)) == "EN140227"  # noqa: SLF001
    assert latest_date == date(2026, 7, 28)
    assert [result.model_dump() for result in latest_results] == [
        {
            "name": "SEDIMENTATION RATE",
            "value": "24",
            "unit": "mm/h",
            "date": "2026-07-28",
            "reference_range": "<20",
        },
        {
            "name": "ALBUMIN",
            "value": "3.5",
            "unit": "g/dL",
            "date": "2026-07-28",
            "reference_range": "3.5-5.2",
        },
        {
            "name": "C REACT.PROTEIN INFLAMM.",
            "value": "24",
            "unit": "mg/L",
            "date": "2026-07-28",
            "reference_range": "< 8.0",
        },
        {
            "name": "eGFR",
            "value": "99",
            "unit": "See note",
            "date": "2026-07-28",
            "reference_range": ">59",
        },
    ]


def test_wound_report_extractor_parses_resident_wounds(
    tmp_path: pathlib.Path,
) -> None:
    extractor = WoundReportExtractor(tmp_path / "wounds.csv")
    text = (
        "CUSTOM Wound Type Tabular Report - WHA,,,,,,,,,,,,,,,,\n"
        ",,,,,,,,,,,,,,,,\n"
        "Patient Number, Name,Room,Bed,Wnd #,Wound Type,Wound Location,"
        "Weeks In Treatment,Wound Progress,Stage,Size (LxWxD) cm,Exudate Type,"
        "Exudate Amt,Tunnelling/ Undermining,Assessment Note,Physician Orders,"
        "Physician Orders Notes\n"
        '180066,"Call, Ernest R",278,B,1,Pressure Injury,"Heel, Left",0,'
        "Initial Exam,Unstageable Pressure Injury Obscured full-thickness skin "
        "and tissue loss,0.8 x 1.5 x 0,,None,,100% Eschar.,"
        "Apply: Skin Prep. Dry Dressing Daily and PRN. Offload. Monitor for "
        "changes.,Notes\n"
        'EN140395,"Daniels, Gloria",284,P,5,Dermatologic,"Ear, Right",24,'
        "No Change,Full Thickness,1 x 2 x 0.3,Sero-sanguineous,Small,,"
        "100% Granulation Tissue.,Cleanse with Saline.,Notes\n"
    )

    residents = extractor._parse_residents(text)  # noqa: SLF001

    assert [resident.facility_id for resident in residents] == ["180066", "EN140395"]
    assert residents[0].resident_name == "Call, Ernest R"
    assert [wound.model_dump() for wound in residents[0].wounds] == [
        {
            "type": "Pressure Injury",
            "location": "Heel, Left",
            "weeks_in_treatment": 0,
            "stage": (
                "Unstageable Pressure Injury Obscured full-thickness skin "
                "and tissue loss"
            ),
            "progress": "Initial Exam",
        },
    ]


def test_order_report_extractor_parses_nutrition_orders(
    tmp_path: pathlib.Path,
) -> None:
    extractor = PccOrderReportExtractor(tmp_path / "orders.pdf")
    resident = "CALL, ERNEST R (180066)"
    text = "\n".join(
        (
            "Resident: CALL, ERNEST R (180066) Order Status: Active",
            "Resident Order Order Order Revision Supply Supply",
            "Name Summary Category Status Date Last Order Date Reorder",
            (
                f"{resident} Acetaminophen Tablet 325 MG Give 2 tablet by "
                "Pharmacy Active 01/07/2026 N"
            ),
            "mouth every 6 hours as needed for pain",
            (
                f"{resident} Dulcolax Suppository Insert 1 suppository "
                "Pharmacy Active 01/07/2026 N"
            ),
            "rectally every 24 hours as needed for constipation",
            (
                f"{resident} Regular diet Chopped texture, Thin consistency "
                "Dietary - Diet Active 07/09/2026 N"
            ),
            (
                f"{resident} Ensure plus PO 8 ounces two times a day for "
                "Dietary - Active 07/09/2026 N"
            ),
            "malnutrition Supplements",
        ),
    )

    resident_name, facility_id = extractor._parse_resident(text)  # noqa: SLF001
    orders = extractor._parse_orders(text, resident_name, facility_id)  # noqa: SLF001

    assert facility_id == "180066"
    assert len(orders) == EXPECTED_ORDER_COUNT
    medications = extractor._extract_medications(orders)  # noqa: SLF001
    assert [medication.name for medication in medications] == [
        "Acetaminophen Tablet 325 MG",
    ]
    assert extractor._extract_diet(orders) == "Regular diet"  # noqa: SLF001
    assert extractor._extract_diet_texture(orders) == "Chopped"  # noqa: SLF001
    assert extractor._extract_liquid_consistency(orders) == "Thin"  # noqa: SLF001
    supplements = extractor._extract_supplements(orders)  # noqa: SLF001
    assert [supplement.model_dump() for supplement in supplements] == [
        {
            "name": "Ensure plus",
            "amount": "8 ounces",
            "frequency": "BID",
        },
    ]


def test_order_report_extractor_includes_insulin_without_oral_route(
    tmp_path: pathlib.Path,
) -> None:
    extractor = PccOrderReportExtractor(tmp_path / "orders.pdf")
    orders = [
        extractor._parse_order_block(  # noqa: SLF001
            [
                "Insulin Glargine Solution Inject 10 unit subcutaneously "
                "Pharmacy Active 01/07/2026 N",
            ],
            "Resident",
        ),
    ]

    medications = extractor._extract_medications(  # noqa: SLF001
        [order for order in orders if order],
    )

    assert len(medications) == EXPECTED_MEDICATION_COUNT
    assert medications[0].route == "insulin"
