from __future__ import annotations

import asyncio
import typing
import warnings
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from ntk.agents.resident_data_agent import (
    RESIDENT_DATA_INSTRUCTIONS,
    ResidentDataAgent,
    ResidentDataDependencies,
    ResidentFileSource,
    resident_data_agent,
)
from ntk.models.resident_data import (
    LabReportExtraction,
    OrderReportExtraction,
    ProgressNote,
    ResidentContext,
    ResidentWoundData,
    SourceReference,
    WeightVitalsExtraction,
    WoundReportExtraction,
)
from ntk.models.sql.resident import (
    LabResult,
    MedicationData,
    Resident,
    ResidentSnapshot,
    SupplementData,
    TubeFeedingData,
    WeightHistoryEntry,
    WoundData,
)

if typing.TYPE_CHECKING:
    import pathlib

CURRENT_WEIGHT = 120
PREVIOUS_WEIGHT = 130
NOTE_TEXT = "Resident seen for nutrition assessment."
WEIGHT_DATE = "2026-08-16"
EXTRACTED_HEIGHT = 72.0
EXTRACTED_AGE = 80
EXTRACTED_FACILITY_ID = "EN140316"
ORDER_FACILITY_ID = "180066"
LAB_FACILITY_ID = "EN140227"
LAB_DATE = "2026-07-28"
WOUND_FACILITY_ID = "180066"


def _context() -> ResidentContext:
    return ResidentContext(
        resident_snapshot=ResidentSnapshot(
            age=80,
            gender="female",
            height=60,
            current_weight=CURRENT_WEIGHT,
            diet="regular",
        ),
    )


def _progress_note() -> ProgressNote:
    extracted_at = datetime(2026, 8, 23, tzinfo=UTC)
    return ProgressNote(
        note_date=extracted_at,
        note_type="Nutrition",
        author="RD",
        note_text=NOTE_TEXT,
        raw_text=NOTE_TEXT,
        source=SourceReference(
            source_name="resident.pdf",
            source_type="PCC Progress Notes *NEW* Report",
            page_start=1,
            page_end=1,
            extracted_at=extracted_at,
        ),
    )


def _weight_entry() -> WeightHistoryEntry:
    return WeightHistoryEntry(
        date=WEIGHT_DATE,
        weight_lb=CURRENT_WEIGHT,
        description="Wheelchair",
    )


def _weight_extraction() -> WeightVitalsExtraction:
    extracted_at = datetime(2026, 8, 23, tzinfo=UTC)
    return WeightVitalsExtraction(
        source=SourceReference(
            source_name="weights.pdf",
            source_type="PCC Weights and Vitals Summary",
            page_start=1,
            page_end=None,
            extracted_at=extracted_at,
        ),
        facility_id=EXTRACTED_FACILITY_ID,
        height=EXTRACTED_HEIGHT,
        age=EXTRACTED_AGE,
        date_of_birth="1946-02-01",
        weight_history=[_weight_entry()],
    )


def _order_extraction() -> OrderReportExtraction:
    extracted_at = datetime(2026, 8, 23, tzinfo=UTC)
    return OrderReportExtraction(
        source=SourceReference(
            source_name="orders.pdf",
            source_type="PCC Order Listing Report",
            page_start=1,
            page_end=None,
            extracted_at=extracted_at,
        ),
        facility_id=ORDER_FACILITY_ID,
        medications=[
            MedicationData(
                name="Acetaminophen Tablet 325 MG",
                dose="2 tablet",
                route="by mouth",
                frequency="every 6 hours",
                indication="pain",
            ),
        ],
        diet="Regular diet",
        diet_texture="Chopped",
        liquid_consistency="Thin",
        supplements=[
            SupplementData(
                name="Ensure plus",
                amount="8 ounces",
                frequency="BID",
            ),
        ],
        tubefeed_order=TubeFeedingData(
            formula="Glucerna 1.5",
            rate="75 mL/hr",
            schedule="continuous",
            flushes="flush 100 mL every 4 hours",
        ),
    )


def _lab_extraction() -> LabReportExtraction:
    extracted_at = datetime(2026, 8, 23, tzinfo=UTC)
    return LabReportExtraction(
        source=SourceReference(
            source_name="labs.pdf",
            source_type="PCC Lab Results Report",
            page_start=1,
            page_end=None,
            extracted_at=extracted_at,
        ),
        facility_id=LAB_FACILITY_ID,
        latest_labs_date=LAB_DATE,
        latest_labs=[
            LabResult(
                name="ALBUMIN",
                value="3.5",
                unit="g/dL",
                date=LAB_DATE,
                reference_range="3.5-5.2",
            ),
        ],
    )


def _wound_extraction() -> WoundReportExtraction:
    extracted_at = datetime(2026, 8, 23, tzinfo=UTC)
    return WoundReportExtraction(
        source=SourceReference(
            source_name="wounds.csv",
            source_type="WHA Wound Type Tabular Report",
            page_start=None,
            page_end=None,
            extracted_at=extracted_at,
        ),
        residents=[
            ResidentWoundData(
                facility_id=WOUND_FACILITY_ID,
                resident_name="Call, Ernest R",
                wounds=[
                    WoundData(
                        type="Pressure Injury",
                        location="Heel, Left",
                        weeks_in_treatment=0,
                        stage="Unstageable",
                        progress="Initial Exam",
                    ),
                ],
            ),
            ResidentWoundData(
                facility_id="EN140395",
                resident_name="Daniels, Gloria",
                wounds=[
                    WoundData(
                        type="Dermatologic",
                        location="Ear, Right",
                        weeks_in_treatment=24,
                        stage="Full Thickness",
                        progress="No Change",
                    ),
                ],
            ),
        ],
    )


class FakeAgent:
    def __init__(self, output: ResidentContext) -> None:
        self.output = output
        self.prompt = ""
        self.dependencies: ResidentDataDependencies | None = None

    async def run(
        self,
        prompt: str,
        *,
        deps: ResidentDataDependencies,
    ) -> object:
        self.prompt = prompt
        self.dependencies = deps
        return SimpleNamespace(output=self.output)


class ExtractorService:
    def __init__(self) -> None:
        self.extractions: list[tuple[pathlib.Path, str | None]] = []

    @staticmethod
    def get_extractor_name(path: pathlib.Path) -> str:
        if "wound" in path.name:
            return "WoundReportExtractor"
        if "weight" in path.name:
            return "PccWeightHistoryExtractor"
        if "lab" in path.name:
            return "PccLabResultsExtractor"
        if "order" in path.name:
            return "PccOrderReportExtractor"
        if path.suffix.lower() == ".csv":
            return "MiscExtractor"
        return "PccProgressNotesExtractor"

    def extract_file(
        self,
        path: pathlib.Path,
        *,
        expected_extractor: str | None = None,
    ) -> object:
        self.extractions.append((path, expected_extractor))
        if expected_extractor == "PccProgressNotesExtractor":
            return [_progress_note()]
        if expected_extractor == "PccWeightHistoryExtractor":
            return _weight_extraction()
        if expected_extractor == "PccLabResultsExtractor":
            return _lab_extraction()
        if expected_extractor == "WoundReportExtractor":
            return _wound_extraction()
        if expected_extractor == "PccOrderReportExtractor":
            return _order_extraction()
        return path.read_text(encoding="utf-8")


class ResidentRepo:
    def __init__(self, resident: Resident | None = None) -> None:
        self.resident = resident
        self.snapshot = ResidentSnapshot(current_weight=PREVIOUS_WEIGHT)

    def get_by_facility_id(self, facility_id: str) -> Resident | None:
        if self.resident and self.resident.facility_id == facility_id:
            return self.resident
        return None

    def get_latest_snapshot(self, _: object) -> ResidentSnapshot:
        return self.snapshot


def test_extract_builds_deterministic_manifest_and_includes_user_context(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "resident.pdf"
    path.write_bytes(b"pdf")
    expected = _context()
    fake = FakeAgent(expected)
    service = ExtractorService()
    extractor = ResidentDataAgent(
        agent=fake,  # ty: ignore[invalid-argument-type]
        extractor_service=service,  # ty: ignore[invalid-argument-type]
    )

    result = asyncio.run(extractor.extract([path], "  recent weight loss  "))

    assert result is expected
    assert "recent weight loss" in fake.prompt
    assert "file_1" in fake.prompt
    assert "resident.pdf" in fake.prompt
    assert "PccProgressNotesExtractor" in fake.prompt
    assert "Deterministic ResidentContext" in fake.prompt
    assert "Raw deterministic extractor output" in fake.prompt
    assert fake.dependencies is not None
    assert fake.dependencies.files["file_1"].path == path
    assert fake.dependencies.extracted_files["file_1"] == [_progress_note()]
    assert service.extractions == [(path, "PccProgressNotesExtractor")]
    assert result.progress_notes[0].note_text == NOTE_TEXT
    assert expected.to_console().startswith("{")


def test_extract_adds_database_context_deterministically(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "resident.pdf"
    path.write_bytes(b"pdf")
    resident = Resident(facility_id="EN140175")
    expected = ResidentContext(resident_info=Resident(facility_id="EN140175"))
    fake = FakeAgent(expected)
    extractor = ResidentDataAgent(
        agent=fake,  # ty: ignore[invalid-argument-type]
        extractor_service=ExtractorService(),  # ty: ignore[invalid-argument-type]
        resident_repo=ResidentRepo(resident),  # ty: ignore[invalid-argument-type]
    )

    result = asyncio.run(extractor.extract([path]))

    assert result.resident_info is resident
    assert result.resident_snapshot.resident_id == resident.id
    assert result.previous_snapshot is not None
    assert result.previous_snapshot.current_weight == PREVIOUS_WEIGHT
    assert result.latest_nutrition_assessment is not None
    assert result.latest_nutrition_assessment.note_text == NOTE_TEXT


def test_extract_preserves_agent_progress_notes_without_duplicates(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "resident.pdf"
    path.write_bytes(b"pdf")
    note = _progress_note()
    expected = ResidentContext(progress_notes=[note])
    fake = FakeAgent(expected)
    extractor = ResidentDataAgent(
        agent=fake,  # ty: ignore[invalid-argument-type]
        extractor_service=ExtractorService(),  # ty: ignore[invalid-argument-type]
    )

    result = asyncio.run(extractor.extract([path]))

    assert result.progress_notes == [note]


def test_extract_adds_weight_history_deterministically(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "weights.pdf"
    path.write_bytes(b"pdf")
    expected = ResidentContext()
    fake = FakeAgent(expected)
    extractor = ResidentDataAgent(
        agent=fake,  # ty: ignore[invalid-argument-type]
        extractor_service=ExtractorService(),  # ty: ignore[invalid-argument-type]
    )

    result = asyncio.run(extractor.extract([path]))

    assert result.resident_info is not None
    assert result.resident_info.facility_id == EXTRACTED_FACILITY_ID
    assert result.resident_snapshot.height == EXTRACTED_HEIGHT
    assert result.resident_snapshot.age == EXTRACTED_AGE
    assert result.resident_snapshot.weight_history == [_weight_entry()]
    assert result.resident_snapshot.current_weight == CURRENT_WEIGHT
    assert result.resident_snapshot.weight_date == date(2026, 8, 16)


def test_extract_normalizes_agent_dict_snapshot_fields_before_serialization(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "resident.pdf"
    path.write_bytes(b"pdf")
    expected = ResidentContext()
    expected.resident_snapshot.weight_history = [  # ty: ignore[invalid-assignment]
        {
            "date": "2026-01-25",
            "weight_lb": 332.8,
            "description": "Mechanical Lift",
        },
    ]
    fake = FakeAgent(expected)
    extractor = ResidentDataAgent(
        agent=fake,  # ty: ignore[invalid-argument-type]
        extractor_service=ExtractorService(),  # ty: ignore[invalid-argument-type]
    )

    result = asyncio.run(extractor.extract([path]))

    assert isinstance(result.resident_snapshot.weight_history[0], WeightHistoryEntry)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result.to_console()
    assert not [
        warning
        for warning in caught
        if "PydanticSerializationUnexpectedValue" in str(warning.message)
    ]


def test_extract_works_with_pydantic_ai_test_model(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "weights.pdf"
    path.write_bytes(b"pdf")
    test_model = TestModel(
        custom_output_args={
            "resident_snapshot": {
                "weight_history": [
                    WeightHistoryEntry(
                        date="2026-01-25",
                        weight_lb=332.8,
                        description="Mechanical Lift",
                    ),
                ],
            },
        },
        model_name="test",
    )
    test_agent = Agent(
        test_model,
        deps_type=ResidentDataDependencies,
        output_type=ResidentContext,
    )
    extractor = ResidentDataAgent(
        agent=test_agent,
        extractor_service=ExtractorService(),  # ty: ignore[invalid-argument-type]
    )

    result = asyncio.run(extractor.extract([path]))

    assert test_model.model_name == "test"
    assert result.resident_snapshot.current_weight == CURRENT_WEIGHT
    assert all(
        isinstance(weight, WeightHistoryEntry)
        for weight in result.resident_snapshot.weight_history
    )


def test_extract_adds_conflict_when_weight_vitals_disagree(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "weights.pdf"
    path.write_bytes(b"pdf")
    expected = ResidentContext(
        resident_info=Resident(facility_id="DIFFERENT"),
        resident_snapshot=ResidentSnapshot(height=60),
    )
    fake = FakeAgent(expected)
    extractor = ResidentDataAgent(
        agent=fake,  # ty: ignore[invalid-argument-type]
        extractor_service=ExtractorService(),  # ty: ignore[invalid-argument-type]
    )

    result = asyncio.run(extractor.extract([path]))

    assert result.resident_info is not None
    assert result.resident_info.facility_id == "DIFFERENT"
    assert {conflict.field for conflict in result.conflicts} >= {
        "resident_info.facility_id",
        "resident_snapshot.height",
    }


def test_extract_adds_order_report_context_deterministically(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "orders.pdf"
    path.write_bytes(b"pdf")
    expected = ResidentContext()
    fake = FakeAgent(expected)
    extractor = ResidentDataAgent(
        agent=fake,  # ty: ignore[invalid-argument-type]
        extractor_service=ExtractorService(),  # ty: ignore[invalid-argument-type]
    )

    result = asyncio.run(extractor.extract([path]))

    assert result.resident_info is not None
    assert result.resident_info.facility_id == ORDER_FACILITY_ID
    assert result.resident_snapshot.medications == _order_extraction().medications
    assert result.resident_snapshot.diet == "Regular diet"
    assert result.resident_snapshot.diet_texture == "Chopped"
    assert result.resident_snapshot.liquid_consistency == "Thin"
    assert result.resident_snapshot.supplements == _order_extraction().supplements
    assert result.resident_snapshot.tubefeed_order == _order_extraction().tubefeed_order


def test_extract_adds_lab_results_context_deterministically(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "labs.pdf"
    path.write_bytes(b"pdf")
    expected = ResidentContext()
    fake = FakeAgent(expected)
    extractor = ResidentDataAgent(
        agent=fake,  # ty: ignore[invalid-argument-type]
        extractor_service=ExtractorService(),  # ty: ignore[invalid-argument-type]
    )

    result = asyncio.run(extractor.extract([path]))

    assert result.resident_info is not None
    assert result.resident_info.facility_id == LAB_FACILITY_ID
    assert result.resident_snapshot.latest_labs_date == date(2026, 7, 28)
    assert result.resident_snapshot.latest_labs == _lab_extraction().latest_labs


def test_extract_adds_only_current_resident_wounds(
    tmp_path: pathlib.Path,
) -> None:
    order_path = tmp_path / "orders.pdf"
    wound_path = tmp_path / "wounds.csv"
    order_path.write_bytes(b"pdf")
    wound_path.write_text("wounds", encoding="utf-8")
    expected = ResidentContext()
    fake = FakeAgent(expected)
    extractor = ResidentDataAgent(
        agent=fake,  # ty: ignore[invalid-argument-type]
        extractor_service=ExtractorService(),  # ty: ignore[invalid-argument-type]
    )

    result = asyncio.run(extractor.extract([order_path, wound_path]))

    assert result.resident_info is not None
    assert result.resident_info.facility_id == WOUND_FACILITY_ID
    assert [wound.model_dump() for wound in result.resident_snapshot.wounds] == [
        {
            "type": "Pressure Injury",
            "location": "Heel, Left",
            "weeks_in_treatment": 0,
            "stage": "Unstageable",
            "progress": "Initial Exam",
        },
    ]


def test_extract_adds_conflict_when_order_report_diet_disagrees(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "orders.pdf"
    path.write_bytes(b"pdf")
    expected = ResidentContext(resident_snapshot=ResidentSnapshot(diet="NAS diet"))
    fake = FakeAgent(expected)
    extractor = ResidentDataAgent(
        agent=fake,  # ty: ignore[invalid-argument-type]
        extractor_service=ExtractorService(),  # ty: ignore[invalid-argument-type]
    )

    result = asyncio.run(extractor.extract([path]))

    assert result.resident_snapshot.diet == "NAS diet"
    assert {conflict.field for conflict in result.conflicts} >= {
        "resident_snapshot.diet",
    }


def test_resident_data_agent_does_not_expose_file_tools() -> None:
    assert not resident_data_agent._function_toolset.tools  # noqa: SLF001


def test_extract_files_reads_unknown_manifest_file_once(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "resident.csv"
    path.write_text("weight_lb\n120", encoding="utf-8")
    service = ExtractorService()
    source = ResidentFileSource(
        file_id="file_1",
        filename=path.name,
        path=path,
        extractor_name="MiscExtractor",
    )
    dependencies = ResidentDataDependencies(
        files={source.file_id: source},
        extractor_service=service,  # ty: ignore[invalid-argument-type]
    )
    extractor = ResidentDataAgent(
        agent=FakeAgent(ResidentContext()),  # ty: ignore[invalid-argument-type]
        extractor_service=service,  # ty: ignore[invalid-argument-type]
    )

    extractor.extract_files(dependencies)
    extractor.extract_files(dependencies)

    assert dependencies.extracted_files[source.file_id] == "weight_lb\n120"
    assert service.extractions == [(path, "MiscExtractor")]


def test_extraction_instructions_define_sources_and_no_persistence() -> None:
    assert "Use the deterministic extractor output provided in the prompt" in (
        RESIDENT_DATA_INSTRUCTIONS
    )
    assert "Deterministic file extractor results are the primary source" in (
        RESIDENT_DATA_INSTRUCTIONS
    )
    assert "Additional user context is supplementary" in RESIDENT_DATA_INSTRUCTIONS
    assert "Never write to a database" in RESIDENT_DATA_INSTRUCTIONS
    assert "Do not look up database values" in RESIDENT_DATA_INSTRUCTIONS


def test_resident_context_maps_identity_and_snapshot_sql_models() -> None:
    facility_id = "EN140175"
    context = ResidentContext(
        resident_info=Resident(facility_id=facility_id),
        resident_snapshot=ResidentSnapshot(current_weight=CURRENT_WEIGHT),
    )

    payload = context.clinical_payload()
    resident_info = typing.cast("dict[str, object]", payload["resident_info"])
    resident_snapshot = typing.cast(
        "dict[str, object]",
        payload["resident_snapshot"],
    )

    assert context.resident_info is not None
    assert context.resident_info.facility_id == facility_id
    assert resident_info["facility_id"] == str(facility_id)
    assert resident_snapshot["current_weight"] == CURRENT_WEIGHT


@pytest.mark.parametrize(
    ("filename", "contents", "message"),
    [
        ("missing.pdf", None, "does not exist"),
        ("resident.txt", b"text", "not a PDF"),
        ("empty.pdf", b"", "is empty"),
    ],
)
def test_extract_rejects_invalid_resident_data_paths(
    tmp_path: pathlib.Path,
    filename: str,
    contents: bytes | None,
    message: str,
) -> None:
    path = tmp_path / filename
    if contents is not None:
        path.write_bytes(contents)
    extractor = ResidentDataAgent(
        agent=FakeAgent(_context()),  # ty: ignore[invalid-argument-type]
        extractor_service=ExtractorService(),  # ty: ignore[invalid-argument-type]
    )

    with pytest.raises(ValueError, match=message):
        asyncio.run(extractor.extract([path]))
