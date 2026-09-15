from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine, select

from api.models.knowledge import KnowledgeChunkCreate, KnowledgeType
from api.models.sql.knowledge import Knowledge, KnowledgeChunk, KnowledgeChunkEmbedding
from api.repositories.knowledge_repo import KnowledgeRepo


def test_knowledge_repo_stores_duplicate_chunks_under_separate_sources() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        repository = KnowledgeRepo(session)
        for file_hash in ("first-file", "second-file"):
            repository.ingest(
                Knowledge(
                    filename=f"{file_hash}.pdf",
                    knowledge_type=KnowledgeType.NUTRITION_CARE_MANUAL,
                    file_hash=file_hash,
                ),
                [
                    KnowledgeChunkCreate(
                        content="Shared educational heading",
                        section_title="Education",
                        source_page_start=4,
                        source_page_end=4,
                    ),
                ],
                [[0.1]],
                "embedding-model",
            )
        knowledge = session.exec(select(Knowledge)).all()
        chunks = session.exec(select(KnowledgeChunk)).all()
        embeddings = session.exec(select(KnowledgeChunkEmbedding)).all()
    assert len(knowledge) == 2  # noqa: PLR2004
    assert len(chunks) == 2  # noqa: PLR2004
    assert len(embeddings) == 2  # noqa: PLR2004
    assert all(chunk.section_title == "Education" for chunk in chunks)
    assert all(chunk.source_page_start == 4 for chunk in chunks)  # noqa: PLR2004
