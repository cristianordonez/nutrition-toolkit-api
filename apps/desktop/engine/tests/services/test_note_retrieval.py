"""NCP history and style examples stay separate from clinical sources."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, create_engine

from engine.models.ncp_note import NCPNoteStatus, NCPNoteType
from engine.models.sql.clinical_source import ClinicalSource, ClinicalSourceKind
from engine.models.sql.ncp_note import NCPNote
from engine.models.sql.person import Person
from engine.repositories.person_repo import PersonRepo
from engine.services.note_retrieval import NoteRetrievalService
from engine.utils.misc import require_id


def _session() -> Session:
    db = create_engine("sqlite://")
    SQLModel.metadata.create_all(db)
    return Session(db)


def _note(
    session: Session,
    person_id: int | None,
    *,
    day: int,
    status: NCPNoteStatus,
    content: str = "note body",
) -> NCPNote:
    timestamp = datetime(2026, 9, day, tzinfo=UTC)
    note = NCPNote(
        person_id=person_id,
        note_type=NCPNoteType.QUARTERLY,
        content=content,
        status=status,
        created_at=timestamp,
        finalized_at=timestamp if status is NCPNoteStatus.FINALIZED else None,
    )
    session.add(note)
    session.commit()
    return note


def test_latest_finalized_ncp_is_previous_note() -> None:
    with _session() as session:
        person = PersonRepo(session).create(Person(name="A", person_identifier="A1"))
        _note(
            session,
            person.id,
            day=1,
            status=NCPNoteStatus.FINALIZED,
            content="older",
        )
        _note(
            session,
            person.id,
            day=20,
            status=NCPNoteStatus.FINALIZED,
            content="newer",
        )

        previous = NoteRetrievalService(session).previous_note(require_id(person.id))

        assert previous is not None
        assert previous.note_text == "newer"
        assert previous.note_date.day == 20  # noqa: PLR2004


def test_drafts_and_examples_are_not_previous_notes() -> None:
    with _session() as session:
        person = PersonRepo(session).create(Person(name="B", person_identifier="B1"))
        _note(session, person.id, day=5, status=NCPNoteStatus.DRAFT)
        _note(session, None, day=6, status=NCPNoteStatus.EXAMPLE)

        assert (
            NoteRetrievalService(session).previous_note(require_id(person.id)) is None
        )


def test_another_persons_ncp_is_never_returned() -> None:
    with _session() as session:
        repository = PersonRepo(session)
        subject = repository.create(Person(name="C", person_identifier="C1"))
        other = repository.create(Person(name="D", person_identifier="D1"))
        _note(session, other.id, day=4, status=NCPNoteStatus.FINALIZED)

        assert (
            NoteRetrievalService(session).previous_note(require_id(subject.id)) is None
        )


def test_progress_note_source_is_not_ncp_history() -> None:
    with _session() as session:
        person = PersonRepo(session).create(Person(name="E", person_identifier="E1"))
        session.add(
            ClinicalSource(
                person_id=person.id,
                source_kind=ClinicalSourceKind.PROGRESS_NOTE,
                effective_at=datetime(2026, 9, 10, tzinfo=UTC),
                note_type="Nutrition/Dietary Note",
                content="Imported nutrition progress note",
                raw_content="Imported nutrition progress note",
                source_key="progress-note",
            ),
        )
        session.commit()

        assert (
            NoteRetrievalService(session).previous_note(require_id(person.id)) is None
        )
