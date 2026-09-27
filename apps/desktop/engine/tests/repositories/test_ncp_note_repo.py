"""Persistence behavior for NCP notes and global examples."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, create_engine

from engine.models.ncp_note import NCPNoteStatus, NCPNoteType
from engine.models.sql.ncp_note import NCPNote
from engine.models.sql.person import Person
from engine.repositories.ncp_note_repo import NCPNoteRepo
from engine.repositories.person_repo import PersonRepo


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_global_example_has_no_person_or_facility() -> None:
    with _session() as session:
        note = NCPNoteRepo(session).save(
            NCPNote(
                note_type=NCPNoteType.ADMISSION,
                content="Bundled admission example",
                status=NCPNoteStatus.EXAMPLE,
            ),
        )

        assert note.person_id is None
        assert note.facility_id is None
        assert note.finalized_at is None


def test_finalize_sets_status_and_timestamp() -> None:
    with _session() as session:
        repository = NCPNoteRepo(session)
        draft = repository.save(
            NCPNote(
                note_type=NCPNoteType.SIGNIFICANT_CHANGE,
                content="Generated draft",
            ),
        )

        finalized = repository.finalize(draft.id)

        assert finalized is draft
        assert finalized.status is NCPNoteStatus.FINALIZED
        assert finalized.finalized_at is not None


def test_latest_finalized_is_scoped_to_person() -> None:
    with _session() as session:
        people = PersonRepo(session)
        subject = people.create(Person(name="Subject", person_identifier="S1"))
        other = people.create(Person(name="Other", person_identifier="O1"))
        repository = NCPNoteRepo(session)
        repository.save(
            NCPNote(
                person_id=subject.id,
                note_type=NCPNoteType.ANNUAL,
                content="older",
                status=NCPNoteStatus.FINALIZED,
                finalized_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        )
        newest = repository.save(
            NCPNote(
                person_id=subject.id,
                note_type=NCPNoteType.QUARTERLY,
                content="newest",
                status=NCPNoteStatus.FINALIZED,
                finalized_at=datetime(2026, 6, 1, tzinfo=UTC),
            ),
        )
        repository.save(
            NCPNote(
                person_id=other.id,
                note_type=NCPNoteType.QUARTERLY,
                content="other",
                status=NCPNoteStatus.FINALIZED,
                finalized_at=datetime(2026, 9, 1, tzinfo=UTC),
            ),
        )

        assert repository.latest_finalized(subject.id) is newest


def test_list_examples_does_not_include_drafts_or_finalized_notes() -> None:
    with _session() as session:
        repository = NCPNoteRepo(session)
        example = repository.save(
            NCPNote(
                note_type=NCPNoteType.QUARTERLY,
                content="example",
                status=NCPNoteStatus.EXAMPLE,
            ),
        )
        repository.save(
            NCPNote(
                note_type=NCPNoteType.QUARTERLY,
                content="draft",
                status=NCPNoteStatus.DRAFT,
            ),
        )

        assert repository.list_examples() == [example]
