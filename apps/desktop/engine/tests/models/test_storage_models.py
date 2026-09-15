from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import SQLModel

from engine.models.sql.person import ExtractionStatus, Person, PersonClinicalNote


def test_person_clinical_note_table_is_lean() -> None:
    assert PersonClinicalNote.__tablename__ == "person_clinical_note"
    assert "nutrition_care_process" not in SQLModel.metadata.tables
    assert "assessment" not in SQLModel.metadata.tables
    columns = PersonClinicalNote.__table__.c  # ty: ignore[unresolved-attribute]
    assert "note_key" in columns
    assert "ncp_source" not in columns
    assert "content_hash" not in columns
    assert "status" not in columns


def test_person_clinical_note_links_to_person() -> None:
    person = Person(id=1, name="Jane Doe")
    note = PersonClinicalNote(
        id=1,
        person_id=1,
        note_date=datetime(2026, 8, 31, tzinfo=UTC),
        note_type="Nutrition/Dietary",
        author="dietitian",
        note_text="Nutrition assessment",
        raw_text="Nutrition assessment",
        note_key="nutrition-note-1",
        extraction_status=ExtractionStatus.EXTRACTED,
        person=person,
    )

    assert note.person is person
    assert note.extraction_status is ExtractionStatus.EXTRACTED
