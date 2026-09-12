from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, create_engine

import ntk.models.sql  # noqa: F401
from ntk.models.sql.person import ExtractionStatus, PersonProgressNote
from ntk.repositories.progress_note_repo import ProgressNoteRepo


def test_create_persists_progress_note_and_get_by_key_finds_it() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = ProgressNoteRepo(session)
        note = PersonProgressNote(
            person_id=1,
            note_date=datetime(2026, 8, 20, tzinfo=UTC),
            note_text="Person consumed 75% of lunch.",
            raw_text="Person consumed 75% of lunch.",
            note_key="note-key-1",
            extraction_status=ExtractionStatus.PENDING,
        )

        created = repository.create(note)

        assert created is note
        assert repository.get_by_key("note-key-1") is note
        assert repository.get_by_key("missing") is None


def test_create_returns_existing_progress_note_with_the_same_key() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = ProgressNoteRepo(session)
        person_id = 1
        original = repository.create(
            PersonProgressNote(
                person_id=person_id,
                note_date=datetime(2026, 8, 20, tzinfo=UTC),
                note_text="Original note text.",
                raw_text="Original note text.",
                note_key="same-note-key",
                extraction_status=ExtractionStatus.PENDING,
            ),
        )
        duplicate = PersonProgressNote(
            person_id=person_id,
            note_date=datetime(2026, 8, 20, tzinfo=UTC),
            note_text="Duplicate note text.",
            raw_text="Duplicate note text.",
            note_key="same-note-key",
            extraction_status=ExtractionStatus.PENDING,
        )

        persisted = repository.create(duplicate)

        assert persisted is original
        assert persisted.note_text == "Original note text."


def test_set_extraction_status_persists_the_new_status() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = ProgressNoteRepo(session)
        note = repository.create(
            PersonProgressNote(
                person_id=1,
                note_date=datetime(2026, 8, 20, tzinfo=UTC),
                note_text="Person consumed 75% of lunch.",
                raw_text="Person consumed 75% of lunch.",
                note_key="status-note",
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
        repository = ProgressNoteRepo(session)
        note = repository.create(
            PersonProgressNote(
                person_id=1,
                note_date=datetime(2026, 9, 1, tzinfo=UTC),
                note_text="Transferred person note.",
                raw_text="Transferred person note.",
                note_key="transferred-note",
                extraction_status=ExtractionStatus.EXTRACTED,
            ),
        )

        updated = repository.update_identity(
            note,
            person_id=2,
        )

        assert updated.person_id == 2  # noqa: PLR2004
