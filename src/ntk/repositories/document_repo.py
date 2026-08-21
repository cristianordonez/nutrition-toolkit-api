"""Persistence operations for retrieval-augmented generation documents."""

from __future__ import annotations

import logging
import typing
from datetime import UTC, datetime
from hashlib import sha256

from sqlmodel import Session, col, delete, select

from ntk.models.document import (
    Document,
    DocumentChunk,
    DocumentEmbedding,
    StoredDocumentType,
)

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class DocumentRepo:
    """Store and resync documents with their extracted text chunks."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def ingest(
        self,
        document: Document,
        chunks: Sequence[DocumentChunk],
        embeddings: Sequence[list[float]],
        model_name: str | None,
        *,
        overwrite: bool = False,
    ) -> Document:
        """Store a document and replace its chunks when it is re-ingested."""
        existing_document = self.find_existing_document(
            document.document_type,
            document.file_hash,
        )
        if existing_document is not None and not overwrite:
            logger.info("Document already ingested; skipping %s", document.filename)
            return existing_document
        if len(chunks) != len(embeddings):
            msg = "Each document chunk must have one embedding"
            raise ValueError(msg)
        if chunks and not model_name:
            msg = "Embedding model name is required"
            raise ValueError(msg)
        resolved_model_name = model_name or ""
        if existing_document is not None:
            existing_document.filename = document.filename
            existing_document.file_hash = document.file_hash
            existing_document.synced_at = datetime.now(UTC)
            logger.info(
                "Existing document found. Deleting previous chunks for %s",
                document.filename,
            )
            self._delete_chunks(existing_document.id)
            document = existing_document
        else:
            logger.info(
                "New document uploaded: %s. Beginning ingestion.",
                document.filename,
            )
        for chunk in chunks:
            chunk.document_id = document.id
        chunk_entries = self._deduplicate_assessment_chunks(
            document.document_type,
            chunks,
            embeddings,
        )
        self.session.add(document)
        self.session.flush()
        chunk_models = [chunk for chunk, _, _ in chunk_entries]
        for index, (chunk, _, content_hash) in enumerate(chunk_entries):
            chunk.chunk_index = index
            chunk.content_hash = content_hash
        self.session.add_all(chunk_models)
        self.session.flush()
        self.session.add_all(
            [
                DocumentEmbedding(
                    document_chunk_id=chunk.id,
                    embedding_vector=embedding,
                    model_name=resolved_model_name,
                )
                for chunk, (_, embedding, _) in zip(
                    chunk_models,
                    chunk_entries,
                    strict=True,
                )
            ],
        )
        self.session.commit()
        self.session.refresh(document)
        return document

    def _deduplicate_assessment_chunks(
        self,
        document_type: StoredDocumentType,
        chunks: Sequence[DocumentChunk],
        embeddings: Sequence[list[float]],
    ) -> list[tuple[DocumentChunk, list[float], str | None]]:
        """Remove assessment chunks whose normalized content is already stored."""
        entries = list(zip(chunks, embeddings, strict=True))
        if document_type is not StoredDocumentType.ASSESSMENT:
            return [(chunk, embedding, None) for chunk, embedding in entries]

        candidates = [
            (chunk, embedding, self._content_hash(chunk))
            for chunk, embedding in entries
        ]
        hashes = {content_hash for _, _, content_hash in candidates}
        existing_hashes = set(
            self.session.exec(
                select(DocumentChunk.content_hash).where(
                    col(DocumentChunk.content_hash).in_(hashes),
                ),
            ).all(),
        )
        accepted_hashes: set[str] = set()
        unique_entries: list[tuple[DocumentChunk, list[float], str | None]] = []
        for chunk, embedding, content_hash in candidates:
            if content_hash in existing_hashes or content_hash in accepted_hashes:
                logger.info("Skipping duplicate assessment chunk: %s", content_hash)
                continue
            accepted_hashes.add(content_hash)
            unique_entries.append((chunk, embedding, content_hash))
        return unique_entries

    @staticmethod
    def _content_hash(chunk: DocumentChunk) -> str:
        """Hash content after normalizing insignificant whitespace."""
        normalized_content = " ".join(chunk.content.split())
        return sha256(normalized_content.encode()).hexdigest()

    def find_existing_document(
        self,
        document_type: StoredDocumentType,
        file_hash: str,
    ) -> Document | None:
        """Find the document to replace for an incoming source."""
        statement = select(Document).where(
            Document.document_type == document_type,
            Document.file_hash == file_hash,
        )
        return self.session.exec(statement).first()

    def count_chunks(self, document_id: object) -> int:
        """Return the number of chunks currently stored for a document."""
        return len(
            self.session.exec(
                select(DocumentChunk.id).where(
                    DocumentChunk.document_id == document_id,
                ),
            ).all(),
        )

    def _delete_chunks(self, document_id: object) -> None:
        """Remove prior chunks and their embeddings before replacing them."""
        chunk_ids = self.session.exec(
            select(DocumentChunk.id).where(DocumentChunk.document_id == document_id),
        ).all()
        msg = f"Deleting {len(chunk_ids)} chunks and associated embeddings"
        logger.debug(msg)
        if chunk_ids:
            logger.debug("Deleting embeddings for document ID=%s", document_id)
            self.session.exec(
                delete(DocumentEmbedding).where(
                    col(DocumentEmbedding.document_chunk_id).in_(chunk_ids),
                ),
            )
        self.session.exec(
            delete(DocumentChunk).where(col(DocumentChunk.document_id) == document_id),
        )
