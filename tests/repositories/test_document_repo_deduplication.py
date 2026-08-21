from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine, select

from ntk.models.document import ChunkType, Document, DocumentChunk, StoredDocumentType
from ntk.repositories.document_repo import DocumentRepo


def _models(
    document_type: StoredDocumentType,
    file_hash: str,
    content: str,
) -> tuple[Document, list[DocumentChunk]]:
    document = Document(
        filename=f"{file_hash}.pdf",
        document_type=document_type,
        file_hash=file_hash,
    )
    return document, [
        DocumentChunk(
            document_id=document.id,
            chunk_index=0,
            chunk_type=(
                ChunkType.ASSESSMENT
                if document_type is StoredDocumentType.ASSESSMENT
                else ChunkType.NUTRITION_CARE_MANUAL
            ),
            content=content,
            metadata={},
        ),
    ]


def test_ingest_does_not_store_duplicate_assessment_content() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = DocumentRepo(session)
        document, chunks = _models(
            StoredDocumentType.ASSESSMENT,
            "first-file",
            "Nutrition assessment\nwith recommendations",
        )
        repository.ingest(document, chunks, [[0.1]], "embedding-model")
        document, chunks = _models(
            StoredDocumentType.ASSESSMENT,
            "second-file",
            " Nutrition  assessment with recommendations ",
        )
        repository.ingest(document, chunks, [[0.2]], "embedding-model")

        stored_chunks = session.exec(select(DocumentChunk)).all()

    assert len(stored_chunks) == 1
    assert stored_chunks[0].content_hash is not None


def test_knowledge_chunks_are_not_globally_deduplicated() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = DocumentRepo(session)
        for file_hash in ("first-knowledge-file", "second-knowledge-file"):
            document, chunks = _models(
                StoredDocumentType.NUTRITION_CARE_MANUAL,
                file_hash,
                "Shared educational heading",
            )
            repository.ingest(document, chunks, [[0.1]], "embedding-model")

        stored_chunks = session.exec(select(DocumentChunk)).all()

    assert len(stored_chunks) == 2  # noqa: PLR2004
    assert all(chunk.content_hash is None for chunk in stored_chunks)
