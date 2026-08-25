from __future__ import annotations

from datetime import UTC, date, datetime

from ntk.models.sql.resident import (
    CsvWoundReportExtraction,
    DialysisData,
    EdemaData,
    LabResult,
    PccLabReportExtraction,
    PccOrder,
    PccOrderReportExtraction,
    PccProgressNotesExtraction,
    PccWeightVitalsExtraction,
    ResidentContext,
    SourceReference,
    WeightHistoryEntry,
    Wound,
)

_AGE = 70
_HEIGHT = 72


def _source(name: str) -> SourceReference:
    return SourceReference(
        source_type="test",
        source=name,
        extracted_at=datetime(2026, 8, 24, tzinfo=UTC),
    )


def test_resident_context_merges_all_supported_extraction_models() -> None:
    context = ResidentContext()
    weight = WeightHistoryEntry(date="2026-08-24", weight_lb=120)
    lab = LabResult(name="Albumin", result="3.0", unit="g/dL")
    order = PccOrder(summary="Renal diet", category="Dietary - Diet")
    wound = Wound(type="Pressure Injury", location="Sacrum", stage="4")

    context.merge_extraction(
        PccWeightVitalsExtraction(
            facility_id="EN140175",
            admission_date=date(2026, 8, 1),
            height=_HEIGHT,
            weight_history=[weight],
            source=_source("weights.pdf"),
        ),
    )
    context.merge_extraction(
        PccProgressNotesExtraction(
            facility_id="EN140175",
            admission_date="2026-08-01",
            age=_AGE,
            gender="Male",
            allergies=["Shellfish"],
            diagnoses=["ESRD"],
            source=_source("progress.pdf"),
        ),
    )
    context.merge_extraction(
        PccOrderReportExtraction(
            facility_id="EN140175",
            orders=[order],
            source=_source("orders.pdf"),
        ),
    )
    context.merge_extraction(
        PccLabReportExtraction(
            facility_id="EN140175",
            admission_date=date(2026, 8, 1),
            age=_AGE,
            lab_results=[lab],
            source=_source("labs.pdf"),
        ),
    )
    context.merge_extraction(
        CsvWoundReportExtraction(
            facility_id="EN140175",
            wounds=[wound],
            source=_source("wounds.csv"),
        ),
    )

    assert context.facility_id == "EN140175"
    assert context.admission_date == date(2026, 8, 1)
    assert context.height == _HEIGHT
    assert context.age == _AGE
    assert context.gender == "Male"
    assert context.weight_history == [weight]
    assert context.labs == [lab]
    assert context.orders == [order]
    assert context.wounds == [wound]
    assert context.allergies == ["Shellfish"]
    assert context.diagnoses == ["ESRD"]
    assert context.conflicts == []


def test_resident_context_records_scalar_conflicts_and_deduplicates_lists() -> None:
    context = ResidentContext()
    first = PccProgressNotesExtraction(
        facility_id="EN140175",
        age=_AGE,
        allergies=["Shellfish"],
        source=_source("first.pdf"),
    )
    second = PccProgressNotesExtraction(
        facility_id="EN999999",
        age=71,
        allergies=["shellfish", "Penicillin"],
        source=_source("second.pdf"),
    )

    context.merge_extraction(first)
    context.merge_extraction(first)
    context.merge_extraction(second)

    assert context.facility_id == "EN140175"
    assert context.age == _AGE
    assert context.allergies == ["Shellfish", "Penicillin"]
    assert {conflict.field for conflict in context.conflicts} == {
        "facility_id",
        "age",
    }
    assert all(
        conflict.values[1].sources == [_source("second.pdf")]
        for conflict in context.conflicts
    )


def test_resident_context_creates_concise_clinical_summary() -> None:
    context = ResidentContext(
        age=_AGE,
        gender="Male",
        admission_date=date(2026, 8, 1),
        height=_HEIGHT,
        diagnoses=["ESRD", "DM2"],
        allergies=["Shellfish"],
        diet="Renal",
        meal_intake="50-75%",
        appetite="Fair",
        diet_restrictions=["Low potassium"],
        weight_history=[
            WeightHistoryEntry(
                date="2026-08-24",
                weight_lb=120,
                description="Wheelchair",
            ),
        ],
        labs=[
            LabResult(
                name="Potassium",
                result="5.7",
                unit="mEq/L",
                flag="H",
                reference_range="3.5-5.1",
                date=datetime(2026, 8, 24, tzinfo=UTC),
            ),
        ],
        orders=[
            PccOrder(
                summary="Renal diet",
                category="Dietary - Diet",
                status="Active",
            ),
        ],
        wounds=[
            Wound(
                type="Pressure Injury",
                location="Sacrum",
                stage="4",
                progress="No Change",
            ),
        ],
        dialysis=DialysisData(type="HD", schedule="T/Th/Sa", dry_weight=52),
        edema=EdemaData(present=True, locations=["Lower extremities"], severity="2+"),
    )

    expected_summary = (
        "Resident: 70-year-old; Male; admitted 2026-08-01; height 72 in\n"
        "Diagnoses: ESRD; DM2\n"
        "Allergies: Shellfish\n"
        "Nutrition: diet Renal; meal intake 50-75%; appetite Fair; "
        "restrictions Low potassium\n"
        "Recent weights: 2026-08-24: 120 lb (Wheelchair)\n"
        "Recent labs: 2026-08-24: Potassium 5.7 mEq/L [H] "
        "(reference 3.5-5.1)\n"
        "Orders: Renal diet [Dietary - Diet, Active]\n"
        "Wounds: Stage 4 Pressure Injury at Sacrum (No Change)\n"
        "Dialysis: HD; T/Th/Sa; dry weight 52\n"
        "Edema: present; Lower extremities; 2+"
    )
    assert context.summary() == expected_summary
    assert ResidentContext().summary() == "No clinical resident data available."
