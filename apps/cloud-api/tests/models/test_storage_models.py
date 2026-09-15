from __future__ import annotations

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlmodel import SQLModel

from api.models.knowledge import KnowledgeType
from api.models.sql._constants import EMBEDDING_DIMENSIONS
from api.models.sql.knowledge import (
    KNOWLEDGE_EMBEDDING_DIMENSIONS,
    Knowledge,
    KnowledgeChunk,
    KnowledgeChunkEmbedding,
)
from api.models.sql.ncp import NutritionCareProcessEmbedding


def test_storage_uses_expected_table_names() -> None:
    assert Knowledge.__tablename__ == "knowledge"
    assert KnowledgeChunk.__tablename__ == "knowledge_chunks"
    assert KnowledgeChunkEmbedding.__tablename__ == "knowledge_chunks_embeddings"
    assert "assessment" not in SQLModel.metadata.tables


def test_knowledge_chunk_and_embedding_link_to_knowledge() -> None:
    knowledge = Knowledge(
        id=1,
        filename="manual.pdf",
        knowledge_type=KnowledgeType.NUTRITION_CARE_MANUAL,
        file_hash="file-hash",
    )
    chunk = KnowledgeChunk(
        id=1,
        knowledge_id=1,
        chunk_index=0,
        content="Clinical guidance",
        section_title="Protein Requirements",
        source_page_start=12,
        source_page_end=13,
    )
    embedding = KnowledgeChunkEmbedding(
        knowledge_chunk_id=1,
        embedding_vector=[0.1, 0.2],
        model_name="text-embedding-3-small",
    )
    knowledge.chunks.append(chunk)

    assert knowledge.chunks == [chunk]
    assert chunk.knowledge is knowledge
    assert chunk.section_title == "Protein Requirements"
    assert chunk.source_page_start == 12  # noqa: PLR2004
    assert chunk.source_page_end == 13  # noqa: PLR2004
    assert embedding.knowledge_chunk_id == chunk.id


def test_embedding_tables_use_indexed_postgres_vectors() -> None:
    assert EMBEDDING_DIMENSIONS == 384  # noqa: PLR2004
    assert KNOWLEDGE_EMBEDDING_DIMENSIONS == 384  # noqa: PLR2004
    dialect = postgresql.dialect()
    expectations = {
        NutritionCareProcessEmbedding: (
            "nutrition_care_process_embeddings",
            "ix_nutrition_care_process_embeddings_vector_hnsw",
            EMBEDDING_DIMENSIONS,
        ),
        KnowledgeChunkEmbedding: (
            "knowledge_chunks_embeddings",
            "ix_knowledge_chunks_embeddings_embedding_vector_hnsw",
            KNOWLEDGE_EMBEDDING_DIMENSIONS,
        ),
    }

    for model, (table_name, index_name, dimensions) in expectations.items():
        table = model.__table__  # ty: ignore[unresolved-attribute]
        table_sql = str(CreateTable(table).compile(dialect=dialect))
        index_sql = {
            str(CreateIndex(index).compile(dialect=dialect)) for index in table.indexes
        }

        assert f"embedding_vector VECTOR({dimensions}) NOT NULL" in table_sql
        assert (
            f"CREATE INDEX {index_name} ON {table_name} USING hnsw "
            "(embedding_vector vector_cosine_ops)"
        ) in index_sql
