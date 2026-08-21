from __future__ import annotations

from datetime import UTC, date
from uuid import UUID

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from ntk.models.document import (
    EMBEDDING_DIMENSIONS,
    ChunkType,
    Document,
    DocumentChunk,
    DocumentEmbedding,
    StoredDocumentType,
)


def test_document_generates_id_and_synced_at() -> None:
    document = Document(
        filename="manual.pdf",
        document_type=StoredDocumentType.NUTRITION_CARE_MANUAL,
        file_hash="abc123",
    )

    assert isinstance(document.id, UUID)
    assert document.synced_at.tzinfo is UTC
    assert document.filename == "manual.pdf"
    assert document.document_type is StoredDocumentType.NUTRITION_CARE_MANUAL
    assert document.file_hash == "abc123"


def test_document_chunk_and_embedding_link_to_their_parents() -> None:
    document = Document(
        filename="manual.pdf",
        document_type=StoredDocumentType.NUTRITION_CARE_MANUAL,
        file_hash="abc123",
    )
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        chunk_type=ChunkType.NUTRITION_CARE_MANUAL,
        content="Nutrition guidance",
        metadata={"page": 1, "assessment_date": date(2026, 8, 18)},
    )
    embedding = DocumentEmbedding(
        document_chunk_id=chunk.id,
        embedding_vector=[0.1, 0.2, 0.3],
        model_name="text-embedding-3-small",
    )

    assert chunk.document_id == document.id
    assert chunk.chunk_metadata == {
        "page": 1,
        "assessment_date": date(2026, 8, 18),
    }
    assert chunk.chunk_metadata["assessment_date"] == date(2026, 8, 18)
    assert chunk.model_dump(by_alias=True)["metadata"] == {
        "page": 1,
        "assessment_date": date(2026, 8, 18),
    }
    assert embedding.document_chunk_id == chunk.id
    assert embedding.embedding_vector == [0.1, 0.2, 0.3]
    assert embedding.model_name == "text-embedding-3-small"


def test_document_embedding_uses_indexed_postgres_vector() -> None:
    dialect = postgresql.dialect()
    table = DocumentEmbedding.__table__  # ty: ignore[unresolved-attribute]
    table_sql = str(CreateTable(table).compile(dialect=dialect))
    index_sql = {
        str(CreateIndex(index).compile(dialect=dialect)) for index in table.indexes
    }

    assert f"embedding_vector VECTOR({EMBEDDING_DIMENSIONS}) NOT NULL" in table_sql
    assert (
        "CREATE INDEX ix_document_embeddings_embedding_vector_hnsw "
        "ON document_embeddings USING hnsw "
        "(embedding_vector vector_cosine_ops)"
    ) in index_sql
