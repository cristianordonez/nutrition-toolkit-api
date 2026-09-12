from __future__ import annotations

from datetime import date

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlmodel import SQLModel

from ntk.models.knowledge import (
    KnowledgeType,
)
from ntk.models.sql.knowledge import (
    KNOWLEDGE_EMBEDDING_DIMENSIONS,
    Knowledge,
    KnowledgeChunk,
    KnowledgeChunkEmbedding,
)
from ntk.models.sql.person import (
    AssessmentSource,
    PersonAssessment,
    PersonAssessmentEmbedding,
)
from ntk.services.embedding_service import EMBEDDING_DIMENSIONS


def test_storage_uses_one_person_assessment_table() -> None:
    assert PersonAssessment.__tablename__ == "person_assessment"
    assert PersonAssessmentEmbedding.__tablename__ == "person_assessment_embeddings"
    assert Knowledge.__tablename__ == "knowledge"
    assert KnowledgeChunk.__tablename__ == "knowledge_chunks"
    assert KnowledgeChunkEmbedding.__tablename__ == "knowledge_chunks_embeddings"
    assert "assessment" not in SQLModel.metadata.tables


def test_assessment_and_embedding_link_directly() -> None:
    assessment = PersonAssessment(
        id=1,
        person_id=1,
        assessment_source=AssessmentSource.IMPORTED,
        source_filename="assessment.pdf",
        assessment_index=0,
        content="Nutrition assessment",
        content_hash="content-hash",
        assessment_date=date(2026, 8, 31),
        created_by="dietitian",
    )
    embedding = PersonAssessmentEmbedding(
        person_assessment_id=1,
        embedding_vector=[0.1, 0.2],
        model_name="text-embedding-3-small",
        person_assessment=assessment,
    )

    assert assessment.assessment_source is AssessmentSource.IMPORTED
    assert assessment.source_filename == "assessment.pdf"
    assert assessment.created_by == "dietitian"
    assert embedding.person_assessment_id == assessment.id
    assert embedding.person_assessment is assessment
    assert assessment.embeddings == [embedding]
    assert "created_by" in PersonAssessment.__table__.c  # ty: ignore[unresolved-attribute]
    assert "assessment" not in SQLModel.metadata.tables
    assert "assessment_embeddings" not in SQLModel.metadata.tables
    foreign_key = next(
        iter(
            PersonAssessmentEmbedding.__table__.c.person_assessment_id.foreign_keys,  # ty: ignore[unresolved-attribute]
        ),
    )
    assert foreign_key.target_fullname == "person_assessment.id"


def test_assessment_sources_are_generated_or_imported() -> None:
    assert list(AssessmentSource) == [
        AssessmentSource.GENERATED,
        AssessmentSource.IMPORTED,
    ]


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
        PersonAssessmentEmbedding: (
            "person_assessment_embeddings",
            "ix_person_assessment_embeddings_embedding_vector_hnsw",
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
