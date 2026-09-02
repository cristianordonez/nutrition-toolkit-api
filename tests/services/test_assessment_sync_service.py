from __future__ import annotations

import asyncio
import typing
from datetime import UTC, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

import ntk.models.sql  # noqa: F401
from ntk.models.sql.resident import (
    ExtractionStatus,
    Resident,
    ResidentAssessment,
    ResidentAssessmentEmbedding,
    ResidentProgressNote,
    StatusType,
)
from ntk.repositories.assessment_repo import AssessmentRepo
from ntk.repositories.progress_note_repo import ProgressNoteRepo
from ntk.services.assessment import AssessmentEmbeddingService, AssessmentSyncService

if typing.TYPE_CHECKING:
    from ntk.services.embedding_service import EmbeddingService


class FakeEmbeddingService:
    """Return deterministic embeddings or fail when requested."""

    embedding_model = "test-embedding-model"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []

    async def get_embedding_async(self, content: str) -> list[float]:
        self.calls.append(content)
        if self.fail:
            msg = "embedding generation failed"
            raise RuntimeError(msg)
        return [0.1, 0.2]


def _create_note(
    session: Session,
    *,
    note_type: str,
    note_text: str = "  Original nutrition assessment.\nKeep exact spacing.  ",
    note_date: datetime = datetime(2026, 8, 28, 14, 30, tzinfo=UTC),
) -> ResidentProgressNote:
    resident = Resident(name="Test Resident")
    session.add(resident)
    session.commit()
    session.refresh(resident)
    note = ProgressNoteRepo(session).create(
        ResidentProgressNote(
            resident_id=typing.cast("int", resident.id),
            note_date=note_date,
            note_type=note_type,
            author="Test Dietitian",
            note_text=note_text,
            raw_text=note_text,
            note_key=f"note-{note_type}",
            extraction_status=ExtractionStatus.EXTRACTED,
        ),
    )
    session.commit()
    session.refresh(note)
    return note


def _build_service(
    session: Session,
    embedding_service: FakeEmbeddingService,
) -> AssessmentSyncService:
    assessment_repository = AssessmentRepo(session)
    assessment_embedding_service = AssessmentEmbeddingService(
        assessment_repository,
        typing.cast("EmbeddingService", embedding_service),
    )
    return AssessmentSyncService(
        ProgressNoteRepo(session),
        assessment_repository,
        assessment_embedding_service,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "note_type",
    [
        "Nutrition/Dietary Note",
        "Dietitian Progress Note",
        "Dietician",
        "Dietitician",
    ],
)
async def test_sync_assessments_async(note_type: str) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        note = _create_note(session, note_type=note_type)
        embedding_service = FakeEmbeddingService()

        result = await _build_service(
            session,
            embedding_service,
        ).sync_assessments()

        assessment = session.exec(select(ResidentAssessment)).one()
        embedding = session.exec(select(ResidentAssessmentEmbedding)).one()
        assert result.scanned == 1
        assert result.assessments_created == 1
        assert result.embeddings_created == 1
        assert result.failed == 0
        assert result.created_assessments == [assessment]
        assert assessment.source_progress_note_id == note.id
        assert embedding.resident_assessment_id == assessment.id
        assert embedding.embedding_vector == [0.1, 0.2]
        assert embedding.model_name == embedding_service.embedding_model
        assert embedding_service.calls == [assessment.content]


def test_non_dietitian_note_is_skipped() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        _create_note(session, note_type="Nursing Progress Note")

        result = asyncio.run(
            _build_service(session, FakeEmbeddingService()).sync_assessments(),
        )

        assert result.scanned == 1
        assert result.skipped_not_nutrition == 1
        assert result.assessments_created == 0
        assert session.exec(select(ResidentAssessment)).all() == []
        assert session.exec(select(ResidentAssessmentEmbedding)).all() == []


def test_running_sync_twice_does_not_duplicate_records() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        _create_note(session, note_type="Nutrition Assessment")
        embedding_service = FakeEmbeddingService()
        service = _build_service(session, embedding_service)

        first = asyncio.run(service.sync_assessments())
        second = asyncio.run(service.sync_assessments())

        assert first.assessments_created == 1
        assert first.embeddings_created == 1
        assert second.assessments_existing == 1
        assert second.embeddings_existing == 1
        assert len(session.exec(select(ResidentAssessment)).all()) == 1
        assert len(session.exec(select(ResidentAssessmentEmbedding)).all()) == 1
        assert len(embedding_service.calls) == 1


def test_existing_assessment_with_missing_embedding_is_repaired() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        note = _create_note(session, note_type="Dietary Assessment")
        assessment_repository = AssessmentRepo(session)
        assessment_repository.create(
            AssessmentSyncService._build_assessment(note),  # noqa: SLF001
        )
        assert session.exec(select(ResidentAssessmentEmbedding)).all() == []

        result = asyncio.run(
            _build_service(session, FakeEmbeddingService()).sync_assessments(),
        )

        assert result.assessments_existing == 1
        assert result.embeddings_created == 1
        assert len(session.exec(select(ResidentAssessment)).all()) == 1
        assert len(session.exec(select(ResidentAssessmentEmbedding)).all()) == 1


def test_sync_does_not_embed_existing_draft_assessment() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        note = _create_note(session, note_type="Dietary Assessment")
        assessment = AssessmentSyncService._build_assessment(note)  # noqa: SLF001
        assessment.status = StatusType.DRAFT
        assessment.finalized_at = None
        AssessmentRepo(session).create(assessment)
        embedding_service = FakeEmbeddingService()

        result = asyncio.run(
            _build_service(session, embedding_service).sync_assessments(),
        )

        assert result.assessments_existing == 1
        assert result.embeddings_created == 0
        assert result.embeddings_existing == 0
        assert embedding_service.calls == []
        assert session.exec(select(ResidentAssessmentEmbedding)).all() == []


def test_embedding_service_rejects_draft_assessment() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        resident = Resident(name="Test Resident")
        session.add(resident)
        session.commit()
        session.refresh(resident)
        assessment = AssessmentRepo(session).create(
            ResidentAssessment(
                resident_id=typing.cast("int", resident.id),
                content="Unapproved draft",
                content_hash="draft-hash",
                assessment_date=datetime(2026, 8, 30, tzinfo=UTC).date(),
                created_by="model",
                status=StatusType.DRAFT,
            ),
        )
        embedding_service = FakeEmbeddingService()

        created = asyncio.run(
            AssessmentEmbeddingService(
                AssessmentRepo(session),
                typing.cast("EmbeddingService", embedding_service),
            ).embed_assessment(assessment),
        )

        assert created is False
        assert embedding_service.calls == []
        assert session.exec(select(ResidentAssessmentEmbedding)).all() == []


def test_assessment_preserves_resident_text_and_effective_date() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    note_text = "  Nutrition assessment verbatim.\nSecond line.  "
    note_date = datetime(2026, 8, 17, 9, 45, tzinfo=UTC)

    with Session(engine) as session:
        note = _create_note(
            session,
            note_type="Dietary Note",
            note_text=note_text,
            note_date=note_date,
        )

        result = asyncio.run(
            _build_service(session, FakeEmbeddingService()).sync_assessments(),
        )
        assessment = result.created_assessments[0]

        assert assessment.resident_id == note.resident_id
        assert assessment.content == note_text
        assert assessment.assessment_date == note_date.date()
        assert assessment.finalized_at is not None
        assert assessment.finalized_at.replace(tzinfo=UTC) == note_date


def test_embedding_failure_leaves_repairable_assessment() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        _create_note(session, note_type="Dietitian Assessment")
        embedding_service = FakeEmbeddingService(fail=True)
        service = _build_service(session, embedding_service)

        failed = asyncio.run(service.sync_assessments())

        assert failed.assessments_created == 1
        assert failed.failed == 1
        assert len(session.exec(select(ResidentAssessment)).all()) == 1
        assert session.exec(select(ResidentAssessmentEmbedding)).all() == []

        embedding_service.fail = False
        repaired = asyncio.run(service.sync_assessments())
        assert repaired.assessments_existing == 1
        assert repaired.embeddings_created == 1
        assert repaired.failed == 0
        assert len(session.exec(select(ResidentAssessment)).all()) == 1
        assert len(session.exec(select(ResidentAssessmentEmbedding)).all()) == 1


def test_sync_assessments_from_synchronous_cli_boundary() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        _create_note(session, note_type="Nutrition Assessment")
        service = _build_service(session, FakeEmbeddingService())

        result = asyncio.run(service.sync_assessments())

        assert result.assessments_created == 1
        assert result.embeddings_created == 1
