from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import SQLModel

from engine.models.sql.clinical_source import (
    ClinicalSource,
    ClinicalSourceKind,
    ExtractionStatus,
)
from engine.models.sql.ncp_note import NCPNote
from engine.models.sql.person import Person


def test_progress_notes_use_the_generic_clinical_source_table() -> None:
    assert ClinicalSource.__tablename__ == "clinical_source"
    assert "nutrition_care_process" not in SQLModel.metadata.tables
    assert "assessment" not in SQLModel.metadata.tables
    columns = ClinicalSource.__table__.c  # ty: ignore[unresolved-attribute]
    assert "source_key" in columns
    assert "ncp_source" not in columns
    assert "content_hash" in columns
    assert "status" not in columns
    assert "embeddings" not in ClinicalSource.__dict__


def test_ncp_notes_use_a_separate_table() -> None:
    assert NCPNote.__tablename__ == "ncp_note"
    columns = NCPNote.__table__.c  # ty: ignore[unresolved-attribute]
    assert set(columns.keys()) == {
        "id",
        "person_id",
        "facility_id",
        "note_type",
        "content",
        "status",
        "created_at",
        "updated_at",
        "finalized_at",
    }
    assert "ncp_note_embedding" not in SQLModel.metadata.tables
    assert "knowledge_chunk_embedding" not in SQLModel.metadata.tables
    assert "embeddings" not in NCPNote.__dict__
    assert "clinical_source_embedding" not in SQLModel.metadata.tables


def test_clinical_source_links_to_person() -> None:
    person = Person(id=1, name="Jane Doe")
    note = ClinicalSource(
        id=1,
        person_id=1,
        source_kind=ClinicalSourceKind.PROGRESS_NOTE,
        effective_at=datetime(2026, 8, 31, tzinfo=UTC),
        note_type="Nutrition/Dietary",
        author="dietitian",
        content="Nutrition assessment",
        raw_content="Nutrition assessment",
        source_key="nutrition-note-1",
        extraction_status=ExtractionStatus.EXTRACTED,
        person=person,
    )

    assert note.person is person
    assert note.extraction_status is ExtractionStatus.EXTRACTED
