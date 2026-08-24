from __future__ import annotations

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlmodel import SQLModel

from ntk.models.knowledge import (
    KnowledgeType,
)
from ntk.models.sql.assessment import (
    ASSESSMENT_EMBEDDING_DIMENSIONS,
    Assessment,
    AssessmentEmbedding,
    AssessmentSource,
)
from ntk.models.sql.knowledge import (
    KNOWLEDGE_EMBEDDING_DIMENSIONS,
    Knowledge,
    KnowledgeChunk,
    KnowledgeChunkEmbedding,
)


def test_storage_uses_separate_assessment_and_knowledge_tables() -> None:
    assert Assessment.__tablename__ == "assessment"
    assert AssessmentEmbedding.__tablename__ == "assessment_embeddings"
    assert Knowledge.__tablename__ == "knowledge"
    assert KnowledgeChunk.__tablename__ == "knowledge_chunks"
    assert KnowledgeChunkEmbedding.__tablename__ == "knowledge_chunks_embeddings"
    assert "document" not in SQLModel.metadata.tables
    assert "document_chunks" not in SQLModel.metadata.tables
    assert "document_embeddings" not in SQLModel.metadata.tables


def test_assessment_and_embedding_link_directly() -> None:
    assessment = Assessment(
        source=AssessmentSource.UPLOADED,
        source_filename="assessment.pdf",
        assessment_index=0,
        content="Nutrition assessment",
        content_hash="content-hash",
        created_by="dietitian",
    )
    embedding = AssessmentEmbedding(
        assessment_id=assessment.id,
        embedding_vector=[0.1, 0.2],
        model_name="text-embedding-3-small",
    )

    assert assessment.source is AssessmentSource.UPLOADED
    assert assessment.source_filename == "assessment.pdf"
    assert assessment.created_by == "dietitian"
    assert embedding.assessment_id == assessment.id
    assert "created_by" in Assessment.__table__.c  # ty: ignore[unresolved-attribute]
    assert "style_source" not in Assessment.__table__.c  # ty: ignore[unresolved-attribute]


def test_knowledge_chunk_and_embedding_link_to_knowledge() -> None:
    knowledge = Knowledge(
        filename="manual.pdf",
        knowledge_type=KnowledgeType.NUTRITION_CARE_MANUAL,
        file_hash="file-hash",
    )
    chunk = KnowledgeChunk(
        knowledge_id=knowledge.id,
        chunk_index=0,
        content="Clinical guidance",
        metadata={"page": 2},
    )
    embedding = KnowledgeChunkEmbedding(
        knowledge_chunk_id=chunk.id,
        embedding_vector=[0.1, 0.2],
        model_name="text-embedding-3-small",
    )
    knowledge.chunks.append(chunk)

    assert knowledge.chunks == [chunk]
    assert chunk.knowledge is knowledge
    assert chunk.chunk_metadata == {"page": 2}
    assert embedding.knowledge_chunk_id == chunk.id


def test_embedding_tables_use_indexed_postgres_vectors() -> None:
    dialect = postgresql.dialect()
    expectations = {
        AssessmentEmbedding: (
            "assessment_embeddings",
            "ix_assessment_embeddings_embedding_vector_hnsw",
            ASSESSMENT_EMBEDDING_DIMENSIONS,
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
