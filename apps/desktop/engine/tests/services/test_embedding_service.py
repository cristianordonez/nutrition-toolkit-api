"""Local NCP-example embedding storage and similarity search."""

from __future__ import annotations

import asyncio

import pytest
import sqlite_vec
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from engine.models.ncp_note import NCPNoteStatus, NCPNoteType
from engine.models.sql.ncp_note import NCPNote
from engine.models.sql.ncp_note_embedding import NCPNoteEmbedding
from engine.services.embedding_service import EmbeddingService
from engine.utils.vector import pack_vector

_DIMENSIONS = 4
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
        return vectors


def _vec_session() -> Session:
    """Return a session with sqlite-vec loaded as it is in production."""
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _load(dbapi_connection, _record) -> None:  # noqa: ANN001
        dbapi_connection.enable_load_extension(True)  # noqa: FBT003
        sqlite_vec.load(dbapi_connection)
        dbapi_connection.enable_load_extension(False)  # noqa: FBT003

    SQLModel.metadata.create_all(engine)
    return Session(engine)


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

        stored = session.exec(select(NCPNoteEmbedding)).all()
        assert added == len(stored) == _NOTE_COUNT
        for row in stored:
            assert row.dimensions == _DIMENSIONS
            assert len(row.vector) == _DIMENSIONS * 4
            assert len(row.to_list()) == _DIMENSIONS


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
    session.add(
        NCPNoteEmbedding(
            ncp_note_id=note_id,
            model="stub-model",
            dimensions=len(vector),
            vector=pack_vector(vector),
        ),
    )
    session.commit()


def _search(session: Session, query: list[float], top_k: int) -> list[int]:
    matches = _StubEmbeddings(session)._search_examples(query, top_k)  # noqa: SLF001
    return [match.document_id for match in matches]


def test_ranking_orders_by_similarity() -> None:
    with _vec_session() as session:
        _stored(session, 1, [0.0, 1.0])
        _stored(session, 2, [1.0, 0.0])
        _stored(session, 3, [1.0, 1.0])

        assert _search(session, [1.0, 0.0], 3) == [2, 3, 1]


def test_ranking_skips_zero_vectors() -> None:
    with _vec_session() as session:
        _stored(session, 1, [0.0, 0.0])
        _stored(session, 2, [1.0, 0.0])

        assert _search(session, [1.0, 0.0], 2) == [2]
        assert _search(session, [0.0, 0.0], 2) == []


def test_ranking_skips_vectors_of_another_width() -> None:
    """sqlite-vec raises on a width mismatch; one such row must not fail search."""
    with _vec_session() as session:
        _stored(session, 1, [1.0, 0.0, 0.0])
        _stored(session, 2, [1.0, 0.0])

        assert _search(session, [1.0, 0.0], 5) == [2]


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

        assert _search(session, [1.0, 0.0], 5) == [1]
