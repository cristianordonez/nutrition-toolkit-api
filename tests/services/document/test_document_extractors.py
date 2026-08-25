from __future__ import annotations

import inspect
import typing
from datetime import UTC, date, datetime

import pymupdf
import pytest

from ntk.models.sql.resident import CsvWoundReportExtraction, PccOrderReportExtraction
from ntk.services.document.document_extractor_service import (
    DocumentExtractorService,
    load_extractors,
)
from ntk.services.document.extractors.base import BaseExtractor
from ntk.services.document.extractors.pcc_lab_results import PccLabResultsExtractor
from ntk.services.document.extractors.pcc_order_report import PccOrderReportExtractor
from ntk.services.document.extractors.pcc_progress_notes import (
    PccProgressNotesExtractor,
)
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
EXPECTED_ORDER_COUNT = 4


def _write_text_pdf(path: pathlib.Path, text: str) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=4000, height=1000)
        page.insert_text((20, 40), text, fontsize=8)
        document.save(path)


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


def test_first_page_text_closes_pdf_and_is_cached(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    class Page:
        @staticmethod
        def get_text() -> str:
            return "Progress Notes *NEW*"

    class Document:
        def __init__(self) -> None:
            self.page_count = 1

        def __enter__(self) -> typing.Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        @staticmethod
        def load_page(page_number: int) -> Page:
            assert page_number == 0
            return Page()

    def open_pdf(_path: pathlib.Path) -> Document:
        nonlocal calls
        calls += 1
        return Document()

    monkeypatch.setattr(
        "ntk.services.document.extractors.base.pymupdf.open",
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


def test_order_report_extract_reads_all_pdf_pages_and_returns_required_fields(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resident = "CALL, ERNEST R (180066)"
    page_texts = [
        "\n".join(
            (
                "Order Listing Report",
                "Resident: CALL, ERNEST R (180066) Order Status: Active",
                (
                    f"{resident} Acetaminophen Tablet 325 MG Give 2 tablets by "
                    "mouth every 6 hours as needed for pain Pharmacy Active "
                    "01/07/2026 N"
                ),
                (
                    f"{resident} Regular diet Chopped texture, Thin consistency "
                    "Dietary - Diet Active 07/09/2026 N"
                ),
            ),
        ),
        "\n".join(
            (
                (
                    f"{resident} Ensure Plus PO 8 ounces two times a day for "
                    "malnutrition Dietary - Supplements Active 07/09/2026 N"
                ),
                (
                    f"{resident} Jevity 1.5 at 60 mL/hr continuous, water flush "
                    "100 mL every 4 hours Enteral Feed Active 07/09/2026 N"
                ),
            ),
        ),
    ]
    loaded_pages: list[int] = []
    was_closed = False

    class Page:
        def __init__(self, text: str) -> None:
            self.text = text

        def get_text(self) -> str:
            return self.text

    class Document:
        page_count = len(page_texts)

        def __enter__(self) -> typing.Self:
            return self

        def __exit__(self, *_args: object) -> None:
            nonlocal was_closed
            was_closed = True

        @staticmethod
        def load_page(page_number: int) -> Page:
            loaded_pages.append(page_number)
            return Page(page_texts[page_number])

    monkeypatch.setattr(
        "ntk.services.document.extractors.base.pymupdf.open",
        lambda _path: Document(),
    )

    result = PccOrderReportExtractor(tmp_path / "orders.pdf").extract()

    assert isinstance(result, PccOrderReportExtraction)
    assert loaded_pages == [0, 0, 1]
    assert was_closed is True
    assert result.facility_id == "180066"
    assert len(result.orders) == EXPECTED_ORDER_COUNT
    assert result.source is not None
    assert result.source.source_type == "PCC Order Listing Report"
    assert result.source.source == str(tmp_path / "orders.pdf")
    assert set(type(result).model_fields) == {"facility_id", "orders", "source"}
    assert [order.category for order in result.orders] == [
        "Pharmacy",
        "Dietary - Diet",
        "Dietary - Supplements",
        "Enteral Feed",
    ]


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
) -> None:
    extractor = PccWeightHistoryExtractor(tmp_path / "weights.pdf")
    text = (
        "Resident: Orosz, Joseph (EN140316) Vital: BMI Percentile, Height, Weight\n"
        "Orosz, Joseph (EN140316) Location: 2B 288 P, "
        f"Height: {EXTRACTED_HEIGHT:g} Inches, "
        "DOA: 08/01/2026"
    )

    assert extractor._parse_facility_id(text) == "EN140316"  # noqa: SLF001
    assert extractor._parse_height(text) == EXTRACTED_HEIGHT  # noqa: SLF001
    assert extractor._parse_admission_date(text) == date(2026, 8, 1)  # noqa: SLF001


def test_weight_history_extracts_pymupdf_rows_and_declared_fields_only(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "weights.pdf"
    with pymupdf.open() as document:
        first_page = document.new_page()
        for point, text in (
            ((20, 40), "Weights and Vitals Summary"),
            ((20, 60), "Resident: Orosz, Joseph (EN140316)"),
            ((20, 80), "DOA: 08/01/2026"),
            ((20, 100), "Height: 72 Inches"),
            ((20, 140), "08/16/2026 09:19"),
            ((180, 140), "332 Lbs"),
            ((250, 140), "(Mechanical Lift)"),
            ((20, 160), "08/16/2026 09:18"),
            ((180, 160), "332 Lbs"),
            ((250, 160), "(Mechanical Lift)"),
            ((20, 180), "08/05/2026 07:19"),
            ((180, 180), "332.2 Lbs"),
            ((250, 180), "(Wheelchair)"),
        ):
            first_page.insert_text(point, text, fontsize=8)
        continuation_page = document.new_page()
        continuation_page.insert_text((20, 40), "08/16/2026 09:19", fontsize=8)
        continuation_page.insert_text((180, 40), "332 Lbs", fontsize=8)
        continuation_page.insert_text((250, 40), "(Mechanical Lift)", fontsize=8)
        document.save(path)

    extraction = PccWeightHistoryExtractor(path).extract()

    assert set(type(extraction).model_fields) == {
        "admission_date",
        "height",
        "facility_id",
        "weight_history",
        "source",
    }
    assert extraction.admission_date == date(2026, 8, 1)
    assert extraction.height == EXTRACTED_HEIGHT
    assert extraction.facility_id == "EN140316"
    assert [entry.model_dump() for entry in extraction.weight_history] == [
        {
            "date": "2026-08-16",
            "weight_lb": 332.0,
            "description": "Mechanical Lift",
        },
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
    assert extraction.source is not None
    assert extraction.source.source == str(path)


def test_progress_notes_extractor_parses_header_metadata(
    tmp_path: pathlib.Path,
) -> None:
    extractor = PccProgressNotesExtractor(tmp_path / "progress-notes.pdf")
    text = (
        "Progress Notes *NEW*\n"
        "Resident : Orosz, Joseph (EN140316) Gender : F "
        "Admission Date : 08/01/2026 Allergies : Shellfish; Penicillin "
        "Diagnoses : CKD, DM2 DOB : 02/01/1946"
    )

    assert extractor._parse_facility_id(text) == "EN140316"  # noqa: SLF001
    assert extractor._parse_report_date(text) == "2026-08-01"  # noqa: SLF001
    assert extractor._parse_gender(text) == "Female"  # noqa: SLF001
    assert extractor._parse_allergies(text) == [  # noqa: SLF001
        "Shellfish",
        "Penicillin",
    ]
    assert extractor._parse_diagnoses(text) == [  # noqa: SLF001
        "CKD",
        "DM2",
    ]


def test_progress_notes_extracts_pymupdf_notes_and_declared_fields_only(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "progress-notes.pdf"

    def add_header(page: pymupdf.Page) -> None:
        for point, text in (
            ((20, 40), "Progress Notes *NEW*"),
            ((20, 60), "Resident: Orosz, Joseph (EN140316) Gender: F"),
            ((20, 80), "Admission Date: 08/01/2026 DOB: 02/01/1946"),
            ((20, 100), "Allergies: Shellfish; Penicillin Diagnoses: CKD, DM2"),
        ):
            page.insert_text(point, text, fontsize=8)

    with pymupdf.open() as document:
        first_page = document.new_page()
        add_header(first_page)
        for point, text in (
            ((20, 140), "Effective Date: 08/20/2026"),
            ((20, 155), "Type: Nutrition Note"),
            ((20, 170), "Author: Jane Doe, RD [Dietitian]"),
            ((20, 185), "Note Text: Resident eating 75% of meals."),
            ((20, 200), "Continue current nutrition plan."),
        ):
            first_page.insert_text(point, text, fontsize=8)
        second_page = document.new_page()
        add_header(second_page)
        for point, text in (
            ((20, 140), "First note continued on page two."),
            ((20, 180), "Effective Date: 08/22/2026"),
            ((20, 195), "Type: Nursing Note"),
            ((20, 210), "Author: John Smith [Nurse]"),
            ((20, 225), "Note Text: No new nutrition concerns."),
        ):
            second_page.insert_text(point, text, fontsize=8)
        document.save(path)
    extraction = PccProgressNotesExtractor(path).extract()
    today = datetime.now(tz=UTC).date()
    expected_age = today.year - 1946 - ((today.month, today.day) < (2, 1))
    assert set(type(extraction).model_fields) == {
        "facility_id",
        "gender",
        "admission_date",
        "age",
        "allergies",
        "diagnoses",
        "progress_notes",
        "source",
    }
    assert extraction.facility_id == "EN140316"
    assert extraction.gender == "Female"
    assert extraction.admission_date == "2026-08-01"
    assert extraction.age == expected_age
    assert extraction.allergies == ["Shellfish", "Penicillin"]
    assert extraction.diagnoses == ["CKD", "DM2"]
    assert len(extraction.progress_notes) == 2  # noqa: PLR2004

    first_note, second_note = extraction.progress_notes
    assert first_note.note_date == datetime(2026, 8, 20, tzinfo=UTC)
    assert first_note.note_type == "Nutrition Note"
    assert first_note.author == "Jane Doe, RD"
    assert "First note continued on page two." in first_note.note_text
    assert second_note.note_date == datetime(2026, 8, 22, tzinfo=UTC)
    assert second_note.note_type == "Nursing Note"
    assert second_note.author == "John Smith"
    assert second_note.note_text == "No new nutrition concerns."
    assert extraction.source is not None
    assert extraction.source.source == str(path)
    assert all(note.source.source == str(path) for note in extraction.progress_notes)


def test_lab_results_extracts_pymupdf_table_rows(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "labs.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        for point, text in (
            ((20, 40), "Lab Results Report"),
            ((20, 60), "Resident: Akhtar, Naseem (EN140427)"),
            ((20, 80), "Collection Date:07/24/2026 13:25"),
            ((20, 100), "Admit Date: 08/22/2026"),
            ((20, 120), "Result for: AKHTAR, NASEEM (DOB 4/4/1954, F)"),
            ((344, 150), "Result"),
            ((396, 150), "Unit"),
            ((440, 150), "Ref. Range"),
            ((516, 150), "Flag"),
            ((559, 150), "Status"),
            ((37, 175), "HEMOGLOBIN"),
            ((356, 175), "9.6"),
            ((399, 175), "g/dL"),
            ((443, 175), "10.7-15.1"),
            ((522, 175), "L"),
            ((561, 175), "Final"),
            ((37, 195), "GLUCOSE"),
            ((356, 195), "172"),
            ((395, 195), "mg/dL"),
            ((445, 195), "65-99"),
            ((522, 195), "H"),
            ((561, 195), "Final"),
        ):
            page.insert_text(point, text, fontsize=8)
        document.save(path)
    extraction = PccLabResultsExtractor(path).extract()
    today = datetime.now(tz=UTC).date()
    expected_age = today.year - 1954 - ((today.month, today.day) < (4, 4))
    assert extraction.facility_id == "EN140427"
    assert extraction.admission_date == date(2026, 8, 22)
    assert extraction.age == expected_age
    assert [result.model_dump() for result in extraction.lab_results] == [
        {
            "name": "HEMOGLOBIN",
            "result": "9.6",
            "unit": "g/dL",
            "flag": "L",
            "reference_range": "10.7-15.1",
            "date": datetime(2026, 7, 24, tzinfo=UTC),
        },
        {
            "name": "GLUCOSE",
            "result": "172",
            "unit": "mg/dL",
            "flag": "H",
            "reference_range": "65-99",
            "date": datetime(2026, 7, 24, tzinfo=UTC),
        },
    ]


def test_wound_report_extractor_returns_updated_model(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "wounds.pdf"
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
        '180066,"Call, Ernest R",278,B,2,Dermatologic,"Ear, Right",24,'
        "No Change,Full Thickness,1 x 2 x 0.3,Sero-sanguineous,Small,,"
        "100% Granulation Tissue.,Cleanse with Saline.,Notes\n"
    )
    _write_text_pdf(path, text)

    extraction = WoundReportExtractor(path).extract()

    assert set(type(extraction).model_fields) == {"facility_id", "wounds", "source"}
    assert extraction.facility_id == "180066"
    assert [wound.model_dump() for wound in extraction.wounds] == [
        {
            "type": "Pressure Injury",
            "location": "Heel, Left",
            "weeks_in_treatment": 0,
            "progress": "Initial Exam",
            "stage": (
                "Unstageable Pressure Injury Obscured full-thickness skin "
                "and tissue loss"
            ),
            "size": "0.8 x 1.5 x 0",
            "assessment_note": "100% Eschar.",
            "physician_orders": (
                "Apply: Skin Prep. Dry Dressing Daily and PRN. Offload. Monitor "
                "for changes."
            ),
            "physician_orders_notes": "Notes",
        },
        {
            "type": "Dermatologic",
            "location": "Ear, Right",
            "weeks_in_treatment": 24,
            "progress": "No Change",
            "stage": "Full Thickness",
            "size": "1 x 2 x 0.3",
            "assessment_note": "100% Granulation Tissue.",
            "physician_orders": "Cleanse with Saline.",
            "physician_orders_notes": "Notes",
        },
    ]
    assert extraction.source is not None
    assert extraction.source.source == str(path)


def test_wound_report_extractor_selects_current_resident_from_shared_report(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "wounds.pdf"
    _write_text_pdf(
        path,
        "CUSTOM Wound Type Tabular Report - WHA,,\n"
        "Patient Number,Wound Type,Wound Location\n"
        "180066,Pressure Injury,Heel\n"
        "EN140395,Dermatologic,Ear\n",
    )

    extraction = DocumentExtractorService().extract_file(
        path,
        expected_extractor="WoundReportExtractor",
        resident_facility_id="EN140395",
    )

    assert isinstance(extraction, CsvWoundReportExtraction)
    assert extraction.facility_id == "EN140395"
    assert [wound.model_dump() for wound in extraction.wounds] == [
        {
            "type": "Dermatologic",
            "location": "Ear",
            "weeks_in_treatment": None,
            "progress": None,
            "stage": None,
            "size": None,
            "assessment_note": None,
            "physician_orders": None,
            "physician_orders_notes": None,
        },
    ]

    fallback = WoundReportExtractor(path).extract()
    assert fallback.facility_id == "180066"
    assert [wound.location for wound in fallback.wounds] == ["Heel"]


def test_order_report_extractor_parses_wrapped_order_rows_without_header_positions(
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
    assert [order.summary for order in orders] == [
        (
            "Acetaminophen Tablet 325 MG Give 2 tablet by "
            "mouth every 6 hours as needed for pain"
        ),
        (
            "Dulcolax Suppository Insert 1 suppository "
            "rectally every 24 hours as needed for constipation"
        ),
        "Regular diet Chopped texture, Thin consistency",
        "Ensure plus PO 8 ounces two times a day for malnutrition",
    ]
    assert [order.category for order in orders] == [
        "Pharmacy",
        "Pharmacy",
        "Dietary - Diet",
        "Dietary - Supplements",
    ]
    assert all(order.status == "Active" for order in orders)
    assert orders[0].revision_date == date(2026, 1, 7)
    assert orders[0].supply_last_order_date is None
    assert orders[0].supply_reorder == "N"


def test_order_report_extractor_parses_optional_supply_date(
    tmp_path: pathlib.Path,
) -> None:
    extractor = PccOrderReportExtractor(tmp_path / "orders.pdf")
    order = extractor._parse_order_text(  # noqa: SLF001
        "Insulin Glargine Pharmacy Active 01/07/2026 01/08/2026 Y",
    )

    assert order is not None
    assert order.summary == "Insulin Glargine"
    assert order.revision_date == date(2026, 1, 7)
    assert order.supply_last_order_date == date(2026, 1, 8)
    assert order.supply_reorder == "Y"
