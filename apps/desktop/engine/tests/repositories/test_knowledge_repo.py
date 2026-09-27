"""Retrieval over the bundled manuals, against real sqlite-vec scoring.

Deliberately not mocked. What is being checked is that the pieces line up: the
``float32`` BLOB the application writes is what ``vec_distance_cosine`` reads,
the per-manual filter narrows candidates before ranking, and the join back to
chunk rows returns the right text. A stub would pass while any of those were
wrong.
"""

from __future__ import annotations

import pathlib
import typing

import pytest
import sqlite_vec
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from engine.models.knowledge import KnowledgeChunkCreate
from engine.models.sql.knowledge import (
    Knowledge,
    KnowledgeChunk,
    KnowledgeChunkEmbedding,
    KnowledgeType,
)
from engine.repositories.knowledge_repo import KnowledgeRepo
from engine.utils.vector import pack_vector

_MODEL = "nomic-embed-text"
_DIMENSIONS = 768


def _vector(lead: float, second: float = 0.0) -> list[float]:
    """A 768-wide vector that differs from its neighbours in two places."""
    values = [0.0] * _DIMENSIONS
    values[0] = lead
    values[1] = second
    return values


def _session(tmp_path: pathlib.Path) -> Session:
    database = create_engine(f"sqlite:///{tmp_path / 'facts.db'}")

    @event.listens_for(database, "connect")
    def _load(dbapi_connection: object, _record: object) -> None:
        dbapi_connection.enable_load_extension(True)  # noqa: FBT003
        sqlite_vec.load(dbapi_connection)
        dbapi_connection.enable_load_extension(False)  # noqa: FBT003

    SQLModel.metadata.create_all(database)
    return Session(database)


def _repo(session: Session) -> KnowledgeRepo:
    return KnowledgeRepo(session, _MODEL)


def _manual(
    session: Session,
    knowledge_type: KnowledgeType,
    passages: list[tuple[str, list[float]]],
) -> None:
    manual = Knowledge(
        filename=f"{knowledge_type.value}.pdf",
        knowledge_type=knowledge_type,
        file_hash=knowledge_type.value,
    )
    session.add(manual)
    session.commit()
    session.refresh(manual)
    for index, (text, vector) in enumerate(passages):
        chunk = KnowledgeChunk(
            knowledge_id=typing.cast("int", manual.id),
            chunk_index=index,
            content=text,
        )
        session.add(chunk)
        session.commit()
        session.refresh(chunk)
        session.add(
            KnowledgeChunkEmbedding(
                knowledge_chunk_id=typing.cast("int", chunk.id),
                model=_MODEL,
                dimensions=_DIMENSIONS,
                vector=pack_vector(vector),
            ),
        )
    session.commit()


def test_search_returns_the_nearest_passage(tmp_path: pathlib.Path) -> None:
    with _session(tmp_path) as session:
        _manual(
            session,
            KnowledgeType.DIET_MANUAL,
            [
                ("Pureed texture guidance", _vector(1.0)),
                ("Nectar-thick liquid guidance", _vector(0.0, 1.0)),
            ],
        )
        found = _repo(session).search(_vector(1.0), 1)

        assert [match.chunk_text for match in found] == ["Pureed texture guidance"]
        assert found[0].knowledge_type is KnowledgeType.DIET_MANUAL
        assert found[0].similarity == pytest.approx(1.0)


def test_search_can_be_restricted_to_one_manual(tmp_path: pathlib.Path) -> None:
    """The agent has a tool per manual, so the filter has to actually bind."""
    with _session(tmp_path) as session:
        _manual(
            session,
            KnowledgeType.DIET_MANUAL,
            [("Diet manual passage", _vector(1.0))],
        )
        _manual(
            session,
            KnowledgeType.NUTRITION_CARE_MANUAL,
            [("Nutrition care passage", _vector(0.99))],
        )
        found = _repo(session).search(
            _vector(1.0),
            5,
            knowledge_type=KnowledgeType.NUTRITION_CARE_MANUAL,
        )

        assert [match.chunk_text for match in found] == ["Nutrition care passage"]


def test_another_models_vectors_are_never_returned(tmp_path: pathlib.Path) -> None:
    """A vector is only comparable to others from the model that produced it."""
    with _session(tmp_path) as session:
        _manual(
            session,
            KnowledgeType.DIET_MANUAL,
            [("Embedded by another model", _vector(1.0))],
        )
        session.exec(  # ty: ignore[no-matching-overload]
            KnowledgeChunkEmbedding.__table__.update().values(model="some-other-model"),
        )
        session.commit()
        assert _repo(session).search(_vector(1.0), 5) == []


def _chunk(text: str, page: int = 1) -> KnowledgeChunkCreate:
    return KnowledgeChunkCreate(
        content=text,
        source_page_start=page,
        source_page_end=page,
    )


def test_ingest_stores_chunks_and_makes_them_searchable(
    tmp_path: pathlib.Path,
) -> None:
    """Ingest and search are one repository, so a write is searchable at once."""
    manual = tmp_path / "diet-manual.pdf"
    manual.write_bytes(b"manual bytes")

    with _session(tmp_path) as session:
        repo = _repo(session)
        stored = repo.ingest(
            repo.create_knowledge(manual, KnowledgeType.DIET_MANUAL),
            [_chunk("Pureed texture guidance"), _chunk("Thin liquid guidance", 2)],
            [_vector(1.0), _vector(0.0, 1.0)],
        )

        assert repo.count_chunks(typing.cast("int", stored.id)) == 2  # noqa: PLR2004
        found = repo.search(_vector(1.0), 1)
        assert [match.chunk_text for match in found] == ["Pureed texture guidance"]
        assert found[0].source_page_start == 1


def test_reingesting_an_unchanged_manual_is_a_no_op(
    tmp_path: pathlib.Path,
) -> None:
    """Identity is the content hash, so nothing is re-chunked or re-embedded."""
    manual = tmp_path / "diet-manual.pdf"
    manual.write_bytes(b"manual bytes")

    with _session(tmp_path) as session:
        repo = _repo(session)
        first = repo.ingest(
            repo.create_knowledge(manual, KnowledgeType.DIET_MANUAL),
            [_chunk("Pureed texture guidance")],
            [_vector(1.0)],
        )
        again = repo.ingest(
            repo.create_knowledge(manual, KnowledgeType.DIET_MANUAL),
            [_chunk("Pureed texture guidance")],
            [_vector(1.0)],
        )

        assert again.id == first.id
        assert repo.count_chunks(typing.cast("int", first.id)) == 1


def test_overwriting_searches_the_new_vectors(tmp_path: pathlib.Path) -> None:
    """Overwriting a manual must rank passages by their replacement vectors.

    SQLite reuses a rowid once its row is gone, so a replacement chunk is
    handed the id its predecessor had. Anything still keyed on the old id
    would describe the new passage with the old passage's meaning. Here the
    two passages swap vectors, so a stale vector returns exactly the wrong
    one of them.
    """
    manual = tmp_path / "diet-manual.pdf"
    manual.write_bytes(b"manual bytes")
    alpha, beta = _vector(1.0), _vector(0.0, 1.0)

    with _session(tmp_path) as session:
        repo = _repo(session)
        repo.ingest(
            repo.create_knowledge(manual, KnowledgeType.DIET_MANUAL),
            [_chunk("Alpha passage"), _chunk("Beta passage", 2)],
            [alpha, beta],
        )
        # Same file, so the same hash: the overwrite path re-chunks in place.
        # The vectors swap, so a stale vector now describes each passage with
        # the other one's meaning.
        repo.ingest(
            repo.create_knowledge(manual, KnowledgeType.DIET_MANUAL),
            [_chunk("Alpha passage"), _chunk("Beta passage", 2)],
            [beta, alpha],
            overwrite=True,
        )

        found = repo.search(beta, 1)

        assert [match.chunk_text for match in found] == ["Alpha passage"]


def test_a_chunk_without_an_embedding_is_refused(tmp_path: pathlib.Path) -> None:
    manual = tmp_path / "diet-manual.pdf"
    manual.write_bytes(b"manual bytes")

    with _session(tmp_path) as session:
        repo = _repo(session)
        with pytest.raises(ValueError, match="one embedding"):
            repo.ingest(
                repo.create_knowledge(manual, KnowledgeType.DIET_MANUAL),
                [_chunk("a"), _chunk("b")],
                [_vector(1.0)],
            )
