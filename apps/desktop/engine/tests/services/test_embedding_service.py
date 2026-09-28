"""Local NCP-example embedding storage and similarity search."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select, update
from sqlmodel import Session, col, delete

from engine.database.bootstrap import upgrade_database
from engine.database.db import create_database_engine
from engine.database.vectors import EMBEDDING_DIMENSIONS, ncp_vectors
from engine.models.ncp_note import NCPNoteStatus, NCPNoteType
from engine.models.sql.ncp_note import NCPNote
from engine.models.sql.person import Person
from engine.repositories.ncp_note_repo import NCPNoteRepo
from engine.services.embedding_service import EmbeddingService

_DIMENSIONS = EMBEDDING_DIMENSIONS
_NOTE_COUNT = 3
_TOP_K = 3


class _StubEmbeddings(EmbeddingService):
    """Embed deterministically from text without loading the real model."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.calls: list[list[str]] = []
        self.embedding_model = "stub-model"

    @property
    def model(self) -> str:
        return "stub-model"

    def _embed_query(self, text: str) -> list[float]:
        return self.get_embeddings([text])[0]

    def get_embeddings(self, contents: list[str]) -> list[list[float]]:
        self.calls.append(contents)
        vectors = []
        for value in contents:
            lowered = value.lower()
            vectors.append(
                [
                    float(lowered.count("weight")),
                    float(lowered.count("wound")),
                    float(lowered.count("diabetes")),
                    1.0,
                ],
            )
        return [_padded(vector) for vector in vectors]


def _vec_session() -> Session:
    """Return a session with sqlite-vec loaded as it is in production."""
    engine = create_database_engine("sqlite://")
    upgrade_database(engine)
    return Session(engine)


def _padded(vector: list[float]) -> list[float]:
    return vector + [0.0] * (_DIMENSIONS - len(vector))


def _session_with_examples() -> Session:
    session = _vec_session()
    for content in (
        "weight weight weight loss review",
        "wound wound care dressing change",
        "diabetes diabetes glucose management",
    ):
        session.add(
            NCPNote(
                note_type=NCPNoteType.QUARTERLY,
                content=content,
                status=NCPNoteStatus.EXAMPLE,
            ),
        )
    session.add(
        NCPNote(
            note_type=NCPNoteType.ANNUAL,
            content="draft content must not be embedded",
            status=NCPNoteStatus.DRAFT,
        ),
    )
    session.commit()
    return session


def test_indexing_stores_one_packed_vector_per_example() -> None:
    with _session_with_examples() as session:
        service = _StubEmbeddings(session)

        added = asyncio.run(service.index_examples())

        stored = (
            session.connection()
            .execute(select(ncp_vectors.c.embedding))
            .scalars()
            .all()
        )
        assert added == len(stored) == _NOTE_COUNT
        for row in stored:
            assert len(row) == _DIMENSIONS * 4
            assert len(memoryview(row).cast("f")) == _DIMENSIONS


def test_indexing_is_incremental() -> None:
    with _session_with_examples() as session:
        service = _StubEmbeddings(session)
        asyncio.run(service.index_examples())
        calls_after_first = len(service.calls)

        added = asyncio.run(service.index_examples())

        assert added == 0
        assert len(service.calls) == calls_after_first


def test_search_ranks_only_explicit_examples() -> None:
    with _session_with_examples() as session:
        service = _StubEmbeddings(session)
        asyncio.run(service.index_examples())

        matches = asyncio.run(
            service.search_examples_async("weight weight weight", top_k=3),
        )

        assert matches[0].chunk_text.startswith("weight")
        assert all("draft content" not in match.chunk_text for match in matches)


def test_search_can_be_restricted_to_one_note_type() -> None:
    """The filter narrows candidates before vec0 applies k, not after."""
    with _session_with_examples() as session:
        session.add(
            NCPNote(
                note_type=NCPNoteType.WOUND,
                content="wound wound wound staging",
                status=NCPNoteStatus.EXAMPLE,
            ),
        )
        session.commit()
        service = _StubEmbeddings(session)
        asyncio.run(service.index_examples())

        matches = asyncio.run(
            service.search_examples_async(
                "weight weight weight",
                top_k=1,
                note_type=NCPNoteType.WOUND,
            ),
        )

        assert [match.chunk_text for match in matches] == ["wound wound wound staging"]


def test_search_without_any_stored_vectors_returns_nothing() -> None:
    with _session_with_examples() as session:
        assert asyncio.run(_StubEmbeddings(session).search_examples_async("x")) == []


def test_search_reports_cosine_similarity() -> None:
    with _session_with_examples() as session:
        service = _StubEmbeddings(session)
        asyncio.run(service.index_examples())

        matches = asyncio.run(service.search_examples_async("weight", top_k=3))

        # Query [1, 0, 0, 1] against the weight note's [3, 0, 0, 1].
        assert matches[0].similarity == pytest.approx(4 / (2**0.5 * 10**0.5))
        similarities = [match.similarity for match in matches]
        assert similarities == sorted(similarities, reverse=True)


def _stored(
    session: Session,
    note_id: int,
    vector: list[float],
    *,
    status: NCPNoteStatus = NCPNoteStatus.EXAMPLE,
) -> None:
    session.add(
        NCPNote(
            id=note_id,
            note_type=NCPNoteType.QUARTERLY,
            content=f"note {note_id}",
            status=status,
        ),
    )
    session.flush()
    note = session.get(NCPNote, note_id)
    assert note is not None
    NCPNoteRepo(session).store_embeddings([note], [_padded(vector)], "stub-model")
    session.commit()


def _search(session: Session, query: list[float], top_k: int) -> list[int]:
    matches = NCPNoteRepo(session).search_examples(_padded(query), top_k, "stub-model")
    return [match.document_id for match in matches]


def test_ranking_orders_by_similarity() -> None:
    with _vec_session() as session:
        _stored(session, 1, [0.0, 1.0])
        _stored(session, 2, [1.0, 0.0])
        _stored(session, 3, [1.0, 1.0])

        assert _search(session, [1.0, 0.0], 3) == [2, 3, 1]


def test_zero_vectors_are_rejected_and_zero_queries_return_no_matches() -> None:
    with _vec_session() as session:
        with pytest.raises(ValueError, match="nonzero"):
            _stored(session, 1, [0.0, 0.0])
        _stored(session, 2, [1.0, 0.0])
        assert _search(session, [0.0, 0.0], 2) == []


def test_vectors_of_another_width_are_rejected() -> None:
    with _vec_session() as session:
        note = NCPNote(
            note_type=NCPNoteType.ANNUAL,
            content="Example",
            status=NCPNoteStatus.EXAMPLE,
        )
        session.add(note)
        session.flush()
        with pytest.raises(ValueError, match="384 embedding dimensions"):
            NCPNoteRepo(session).store_embeddings([note], [[1.0, 0.0]], "stub-model")
        assert (
            session.connection().execute(select(ncp_vectors.c.ncp_note_id)).all() == []
        )


def test_ranking_returns_at_most_top_k() -> None:
    with _vec_session() as session:
        for note_id in range(1, 11):
            _stored(session, note_id, [float(note_id), 1.0])

        assert len(_search(session, [1.0, 0.0], _TOP_K)) == _TOP_K
        assert len(_search(session, [1.0, 0.0], 99)) == 10  # noqa: PLR2004


def test_ranking_ignores_notes_that_are_not_examples() -> None:
    with _vec_session() as session:
        _stored(session, 1, [1.0, 0.0])
        _stored(session, 2, [1.0, 0.0], status=NCPNoteStatus.DRAFT)

        assert _search(session, [1.0, 0.0], 1) == [1]


def test_ranking_excludes_another_model_before_limiting() -> None:
    with _vec_session() as session:
        _stored(session, 1, [1.0, 0.0])
        _stored(session, 2, [0.5, 1.0])
        session.exec(
            update(ncp_vectors)
            .where(ncp_vectors.c.ncp_note_id == 1)
            .values(model="other-model"),
        )
        session.commit()
        assert _search(session, [1.0, 0.0], 1) == [2]


def test_changed_content_invalidates_vector_and_can_be_reindexed() -> None:
    with _session_with_examples() as session:
        service = _StubEmbeddings(session)
        asyncio.run(service.index_examples())
        note = session.get(NCPNote, 1)
        assert note is not None
        note.content = "wound care"
        NCPNoteRepo(session).save(note)
        pending = service.notes.unembedded_examples(service.model, limit=None)
        assert [item.id for item in pending] == [1]
        assert asyncio.run(service.index_examples()) == 1


def test_deleting_person_cascades_to_note_vectors_and_rollback_restores_them() -> None:
    with _vec_session() as session:
        person = Person(name="Example person")
        session.add(person)
        session.flush()
        note = NCPNote(
            person_id=person.id,
            note_type=NCPNoteType.ANNUAL,
            content="weight review",
            status=NCPNoteStatus.EXAMPLE,
        )
        session.add(note)
        session.flush()
        repo = NCPNoteRepo(session)
        repo.store_embeddings([note], [_padded([1.0, 0.0])], "stub-model")
        session.commit()
        # Core deletion exercises SQLite's FK cascade, including the trigger.
        delete_person = delete(Person).where(col(Person.id) == person.id)
        session.exec(delete_person)
        assert not repo.has_example_embeddings("stub-model")
        session.rollback()
        assert repo.has_example_embeddings("stub-model")
        session.exec(delete_person)
        session.commit()
        assert (
            session.connection().execute(select(ncp_vectors.c.ncp_note_id)).all() == []
        )
