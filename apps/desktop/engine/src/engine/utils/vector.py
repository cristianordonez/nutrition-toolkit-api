"""Compact storage and similarity scoring for local float32 embedding vectors."""

from __future__ import annotations

import array
import typing

from sqlalchemy import case, func

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Mapped
    from sqlalchemy.sql.elements import ColumnElement

_ELEMENT_TYPE = "f"


def pack_vector(values: list[float]) -> bytes:
    """Pack a vector into a float32 BLOB."""
    return array.array(_ELEMENT_TYPE, values).tobytes()


def unpack_vector(value: bytes) -> list[float]:
    """Unpack a persisted float32 vector."""
    values = array.array(_ELEMENT_TYPE)
    values.frombytes(value)
    return list(values)


def cosine_distance(
    vector: Mapped[bytes],
    dimensions: Mapped[int],
    query_vector: list[float],
) -> ColumnElement[float]:
    """Build sqlite-vec's cosine distance from a stored vector to the query.

    Scored directly against the packed BLOB column: there is no ``vec0``
    index table to keep in step with the rows it indexes.

    ``NULL`` means "not comparable", and callers drop those rows. sqlite-vec
    raises on vectors of different widths, so a row whose width does not
    match the query is never passed to it -- that only happens if an
    embedding model changed its dimensions without changing its name, and
    one such row would otherwise fail the whole search. sqlite-vec itself
    returns ``NULL`` when either vector is all zeros.
    """
    return case(
        (
            dimensions == len(query_vector),
            func.vec_distance_cosine(vector, pack_vector(query_vector)),
        ),
        else_=None,
    )


__all__ = ["cosine_distance", "pack_vector", "unpack_vector"]
