from __future__ import annotations

import typing
from functools import cached_property

from ntk.models.document import ChunkType, Document, DocumentChunk, DocumentType
from ntk.utils.pdf_reader import PdfReader

if typing.TYPE_CHECKING:
    import pathlib
    from collections.abc import Sequence

    from ntk.services.open_ai_service import OpenAIService


class BaseProcessor:
    """Read and validate one supported source-document format."""

    document_type: DocumentType
    format_markers: tuple[str, ...] = ()

    def __init__(self, path: pathlib.Path) -> None:
        """Init base class.

        :param path: full path to document
        """
        self.path = path

    @cached_property
    def pdf_reader(self) -> PdfReader:
        """Return the unopinionated PDF reader for this source."""
        return PdfReader(self.path)

    @cached_property
    def page_texts(self) -> list[str]:
        """Read page text using the mechanism appropriate for this processor."""
        if self.path.suffix.lower() == ".pdf":
            return [page.extract_text() or "" for page in self.pdf_reader.pages]
        if self.path.suffix.lower() == ".txt" and self.path.is_file():
            return [self.path.read_text(encoding="utf-8-sig")]
        msg = f"Unsupported document file type: {self.path}"
        raise ValueError(msg)

    @property
    def text(self) -> str:
        """Join text extracted by this processor."""
        return "\n".join(self.page_texts)

    def validate(self) -> None:
        """Verify that the source has text and expected format markers."""
        normalized_text = self.text.strip().casefold()
        if not normalized_text:
            msg = f"{self.document_type.value} document contains no text"
            raise ValueError(msg)
        if self.format_markers and not any(
            marker in normalized_text for marker in self.format_markers
        ):
            msg = f"Document does not match {self.document_type.value} format"
            raise ValueError(msg)


class IngestionProcessor(BaseProcessor):
    """Create searchable chunks for a document that can be persisted."""

    chunk_type: ChunkType

    def create_chunks(self, document: Document) -> list[DocumentChunk]:
        """Create one chunk containing the complete document by default."""
        return self._create_chunk(document, 0, self.text)

    @staticmethod
    def create_embeddings(
        chunks: Sequence[DocumentChunk],
        open_ai_service: OpenAIService,
    ) -> list[list[float]]:
        """Create one embedding for each chunk in chunk order."""
        return [open_ai_service.create_embedding(chunk.content) for chunk in chunks]

    def _create_chunk(
        self,
        document: Document,
        chunk_index: int,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> list[DocumentChunk]:
        content = content.strip()
        if not content:
            return []
        return [
            DocumentChunk(
                document_id=document.id,
                chunk_index=chunk_index,
                chunk_type=self.chunk_type,
                content=content,
                metadata=metadata or {},
            ),
        ]


class PatientDataProcessor(BaseProcessor):
    """Represent a report that will support patient-data extraction."""

    def extract_patient_data(self) -> None:
        """Extract patient data from the source document."""
        pass  # noqa: PIE790


class IngestiblePatientDataProcessor(IngestionProcessor, PatientDataProcessor):
    """Support ingestion now and patient extraction in a future job."""
