from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, create_engine

import engine.models.sql  # noqa: F401
from engine.models.sql.clinical_source import (
    ClinicalSource,
    ClinicalSourceKind,
    ExtractionStatus,
)
from engine.repositories.clinical_source_repo import ClinicalSourceRepo


def test_create_persists_clinical_note_and_get_by_key_finds_it() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = ClinicalSourceRepo(session)
        note = ClinicalSource(
            person_id=1,
            source_kind=ClinicalSourceKind.PROGRESS_NOTE,
            effective_at=datetime(2026, 8, 20, tzinfo=UTC),
            content="Person consumed 75% of lunch.",
            raw_content="Person consumed 75% of lunch.",
            source_key="note-key-1",
            extraction_status=ExtractionStatus.PENDING,
        )

        created = repository.create(note)

        assert created is note
        assert repository.get_by_key("note-key-1") is note
        assert repository.get_by_key("missing") is None


def test_create_returns_existing_clinical_note_with_the_same_key() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = ClinicalSourceRepo(session)
        person_id = 1
        original = repository.create(
            ClinicalSource(
                person_id=person_id,
                source_kind=ClinicalSourceKind.PROGRESS_NOTE,
                effective_at=datetime(2026, 8, 20, tzinfo=UTC),
                content="Original note text.",
                raw_content="Original note text.",
                source_key="same-note-key",
                extraction_status=ExtractionStatus.PENDING,
            ),
        )
        duplicate = ClinicalSource(
            person_id=person_id,
            source_kind=ClinicalSourceKind.PROGRESS_NOTE,
            effective_at=datetime(2026, 8, 20, tzinfo=UTC),
            content="Duplicate note text.",
            raw_content="Duplicate note text.",
            source_key="same-note-key",
            extraction_status=ExtractionStatus.PENDING,
        )

        persisted = repository.create(duplicate)

        assert persisted is original
        assert persisted.note_text == "Original note text."


def test_set_extraction_status_persists_the_new_status() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = ClinicalSourceRepo(session)
        note = repository.create(
            ClinicalSource(
                person_id=1,
                source_kind=ClinicalSourceKind.PROGRESS_NOTE,
                effective_at=datetime(2026, 8, 20, tzinfo=UTC),
                content="Person consumed 75% of lunch.",
                raw_content="Person consumed 75% of lunch.",
                source_key="status-note",
                extraction_status=ExtractionStatus.PENDING,
            ),
        )

        repository.set_extraction_status(note, ExtractionStatus.EXTRACTED)

        stored = repository.get_by_key("status-note")
        assert stored is not None
        assert stored.extraction_status is ExtractionStatus.EXTRACTED


def test_update_identity_corrects_existing_note_ownership() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = ClinicalSourceRepo(session)
        note = repository.create(
            ClinicalSource(
                person_id=1,
                source_kind=ClinicalSourceKind.PROGRESS_NOTE,
                effective_at=datetime(2026, 9, 1, tzinfo=UTC),
                content="Transferred person note.",
                raw_content="Transferred person note.",
                source_key="transferred-note",
                extraction_status=ExtractionStatus.EXTRACTED,
            ),
        )

        updated = repository.update_identity(
            note,
            person_id=2,
        )

        assert updated.person_id == 2  # noqa: PLR2004
