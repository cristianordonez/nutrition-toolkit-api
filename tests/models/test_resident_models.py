from __future__ import annotations

from datetime import UTC, date
from uuid import UUID

from sqlalchemy import JSON
from sqlalchemy.types import TypeDecorator
from sqlmodel import Session, create_engine

from ntk.models.sql.resident import (
    Resident,
    ResidentSnapshot,
    ResidentSnapshotAssessment,
)

_WEIGHT_LB = 130


def test_resident_snapshot_models_use_expected_tables_and_foreign_keys() -> None:
    resident_table = Resident.__table__  # ty: ignore[unresolved-attribute]
    snapshot_table = ResidentSnapshot.__table__  # ty: ignore[unresolved-attribute]
    assessment_table = ResidentSnapshotAssessment.__table__  # ty: ignore[unresolved-attribute]

    assert resident_table.name == "resident"
    assert snapshot_table.name == "resident_snapshot"
    assert assessment_table.name == "resident_snapshot_assessment"
    assert {
        key.target_fullname for key in snapshot_table.c.resident_id.foreign_keys
    } == {"resident.id"}
    assert {
        key.target_fullname
        for key in assessment_table.c.resident_snapshot_id.foreign_keys
    } == {"resident_snapshot.id"}


def test_resident_snapshot_defaults_support_incomplete_extracted_data() -> None:
    resident = Resident(facility_id="EN140175")
    snapshot = ResidentSnapshot(resident_id=resident.id)
    assessment = ResidentSnapshotAssessment(
        resident_snapshot_id=snapshot.id,
        content="Nutrition assessment",
        model_name="gpt-4.1",
    )

    assert isinstance(resident.id, UUID)
    assert resident.created_at.tzinfo is UTC
    assert snapshot.weight_history == []
    assert snapshot.labs == []
    assert snapshot.diagnoses == []
    assert snapshot.orders == []
    assert snapshot.allergies == []
    assert snapshot.wounds == []
    assert snapshot.edema.present is None
    assert snapshot.dialysis.type is None
    assert snapshot.food_preferences == []
    assert snapshot.diet_restrictions == []
    assert assessment.resident_snapshot_id == snapshot.id
    assert assessment.created_at.tzinfo is UTC


def test_resident_snapshot_preserves_current_structured_fields() -> None:
    snapshot = ResidentSnapshot.model_validate(
        {
            "weight_history": [
                {"date": "2026-07-21", "weight_lb": _WEIGHT_LB},
            ],
            "labs": [{"name": "Albumin", "result": "3.0", "unit": "g/dL"}],
            "admission_date": date(2025, 1, 1),
            "age": 82,
            "gender": "female",
            "height": 62.0,
            "diagnoses": ["T2DM"],
            "orders": [{"summary": "Renal diet"}],
            "allergies": ["shellfish"],
            "wounds": [
                {
                    "type": "pressure injury",
                    "location": "sacrum",
                    "stage": "3",
                },
            ],
            "diet": "CCD",
            "meal_intake": "75%",
            "food_preferences": ["yogurt"],
            "diet_restrictions": ["concentrated sweets"],
            "edema": {"present": True, "severity": "1+"},
            "dialysis": {"type": "HD", "dry_weight": 118.0},
            "readmission_date": date(2026, 8, 1),
        },
    )

    assert snapshot.weight_history[0].weight_lb == _WEIGHT_LB
    assert snapshot.labs[0].name == "Albumin"
    assert snapshot.orders[0].summary == "Renal diet"
    assert snapshot.wounds[0].stage == "3"
    assert snapshot.edema.present is True
    assert snapshot.dialysis.type == "HD"
    assert snapshot.dialysis.dry_weight == 118.0  # noqa: PLR2004
    for field_name in (
        "weight_history",
        "labs",
        "diagnoses",
        "orders",
        "allergies",
        "wounds",
        "food_preferences",
        "diet_restrictions",
        "edema",
        "dialysis",
    ):
        column_type = ResidentSnapshot.__table__.c[field_name].type  # ty: ignore[unresolved-attribute]
        assert isinstance(column_type, (JSON, TypeDecorator))


def test_resident_snapshot_restores_typed_json_after_database_load() -> None:
    engine = create_engine("sqlite://")
    Resident.__table__.create(engine)  # ty: ignore[unresolved-attribute]
    ResidentSnapshot.__table__.create(engine)  # ty: ignore[unresolved-attribute]
    resident = Resident(facility_id="EN140175")
    snapshot = ResidentSnapshot.model_validate(
        {
            "resident_id": resident.id,
            "weight_history": [
                {"date": "2026-07-21", "weight_lb": _WEIGHT_LB},
            ],
            "labs": [{"name": "Albumin", "result": "3.0"}],
            "orders": [{"summary": "Renal diet"}],
            "wounds": [{"type": "Pressure Injury", "location": "Sacrum"}],
            "edema": {"present": True},
            "dialysis": {"type": "HD"},
        },
    )

    with Session(engine) as session:
        session.add(resident)
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)

    assert snapshot.weight_history[0].weight_lb == _WEIGHT_LB
    assert snapshot.labs[0].name == "Albumin"
    assert snapshot.orders[0].summary == "Renal diet"
    assert snapshot.wounds[0].location == "Sacrum"
    assert snapshot.edema.present is True
    assert snapshot.dialysis.type == "HD"
