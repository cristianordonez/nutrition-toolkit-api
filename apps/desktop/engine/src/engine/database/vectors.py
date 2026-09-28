"""Query shapes for vector tables owned exclusively by Alembic migrations.

These lightweight SQL expressions never register tables on SQLModel metadata
or create schema. The model and width must agree with the vector revision;
changing the embedding model requires a migration and re-embedding.
"""

from __future__ import annotations

import array
import math

from sqlalchemy import Float, Integer, LargeBinary, String, column, table

_ELEMENT_TYPE = "f"
EMBEDDING_MODEL = "sentence-transformers:sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384

knowledge_vectors = table(
    "knowledge_chunk_vector",
    column("knowledge_chunk_id", Integer),
    column("embedding", LargeBinary),
    column("model", String),
    column("distance", Float),
    column("k", Integer),
)
ncp_vectors = table(
    "ncp_note_vector",
    column("ncp_note_id", Integer),
    column("embedding", LargeBinary),
    column("model", String),
    column("distance", Float),
    column("k", Integer),
)


def pack_vector(values: list[float]) -> bytes:
    """Pack a vector into a float32 BLOB."""
    return array.array(_ELEMENT_TYPE, values).tobytes()


def pack_embedding(values: list[float]) -> bytes:
    """Validate the fixed-width cosine embedding before writing or searching."""
    if len(values) != EMBEDDING_DIMENSIONS:
        msg = f"Expected {EMBEDDING_DIMENSIONS} embedding dimensions, got {len(values)}"
        raise ValueError(msg)
    if not all(math.isfinite(value) for value in values) or not any(values):
        msg = "Cosine embeddings must be finite and nonzero"
        raise ValueError(msg)
    return pack_vector(values)
