from __future__ import annotations

import asyncio
import typing
from datetime import UTC, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from ntk.models.sql.person import (
    ExtractionStatus,
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
    NutritionClinicalNoteType,
    Person,
    PersonClinicalNote,
    PersonNutritionClinicalNoteEmbedding,
)
from ntk.pipelines.ncp import NutritionCareProcessPipeline
from ntk.repositories.clinical_note_repo import ClinicalNoteRepo

if typing.TYPE_CHECKING:
    from ntk.services.embedding_service import EmbeddingService


class FakeEmbeddingService:
    embedding_model = "test-embedding"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []

    async def get_embedding_async(self, content: str) -> list[float]:
        self.calls.append(content)
        if self.fail:
            msg = "embedding failed"
            raise RuntimeError(msg)
        return [0.1, 0.2]


def _create_note(session: Session, note_type: str) -> PersonClinicalNote:
    person = Person(name="Test Person")
    session.add(person)
    session.commit()
    session.refresh(person)
    note = ClinicalNoteRepo(session).create(
        PersonClinicalNote(
            person_id=typing.cast("int", person.id),
            note_date=datetime(2026, 8, 28, 14, 30, tzinfo=UTC),
            note_type=note_type,
            author="Test Dietitian",
            note_text="Original nutrition assessment.",
            raw_text="Original nutrition assessment.",
            note_key=f"note-{note_type}",
            extraction_status=ExtractionStatus.EXTRACTED,
        ),
    )
    session.commit()
    return note


def _pipeline(
    session: Session,
    embeddings: FakeEmbeddingService,
) -> NutritionCareProcessPipeline:
    return NutritionCareProcessPipeline(
        ClinicalNoteRepo(session),
        embedding_service=typing.cast("EmbeddingService", embeddings),
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("note_type", "expected_type"),
    [
        ("Nutrition/Dietary", NutritionClinicalNoteType.NUTRITION_DIETARY),
        ("Nutrition/Dietary Note", NutritionClinicalNoteType.NUTRITION_DIETARY),
        ("Dietician", NutritionClinicalNoteType.DIETICIAN),
        ("Dietitian Progress Note", NutritionClinicalNoteType.DIETICIAN),
    ],
)
async def test_sync_promotes_eligible_note_in_place(
    note_type: str,
    expected_type: NutritionClinicalNoteType,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        note = _create_note(session, note_type)
        embeddings = FakeEmbeddingService()
        result = await _pipeline(session, embeddings).sync_ncps()
        stored_notes = session.exec(select(PersonClinicalNote)).all()
        embedding = session.exec(select(PersonNutritionClinicalNoteEmbedding)).one()
        assert stored_notes == [note]
        assert note.ncp_source is NutritionCareProcessSource.IMPORTED
        assert note.status is NutritionCareProcessStatus.FINALIZED
        assert result.ncps_created == 1
        assert result.created_ncps == [note]
        assert embedding.person_clinical_note_id == note.id
        assert embedding.type is expected_type
        assert embeddings.calls == [note.note_text]


@pytest.mark.parametrize(
    "note_type",
    [
        "Nursing Progress Note",
        "Nutrition Assessment",
        "Dietary Assessment",
        "Dietitician",
    ],
)
def test_sync_rejects_noncanonical_nutrition_types(note_type: str) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        note = _create_note(session, note_type)
        result = asyncio.run(_pipeline(session, FakeEmbeddingService()).sync_ncps())
        assert note.ncp_source is None
        assert result.skipped_not_nutrition == 1
        assert session.exec(select(PersonNutritionClinicalNoteEmbedding)).all() == []


def test_sync_is_idempotent_and_repairs_missing_embedding() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        note = _create_note(session, "Nutrition/Dietary")
        embeddings = FakeEmbeddingService(fail=True)
        pipeline = _pipeline(session, embeddings)
        failed = asyncio.run(pipeline.sync_ncps())
        assert failed.ncps_created == 1
        assert failed.failed == 1
        assert note.ncp_source is NutritionCareProcessSource.IMPORTED
        embeddings.fail = False
        repaired = asyncio.run(pipeline.sync_ncps())
        repeated = asyncio.run(pipeline.sync_ncps())
        assert repaired.ncps_existing == 1
        assert repaired.embeddings_created == 1
        assert repeated.embeddings_existing == 1
        assert len(session.exec(select(PersonClinicalNote)).all()) == 1
        assert (
            len(session.exec(select(PersonNutritionClinicalNoteEmbedding)).all()) == 1
        )
