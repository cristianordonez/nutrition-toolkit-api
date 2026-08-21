from __future__ import annotations

from ntk.models.document import ChunkType, DocumentType

from .base import IngestionProcessor


class AssessmentProcessor(IngestionProcessor):
    """Process a document containing a single assessment."""

    document_type = DocumentType.ASSESSMENT
    chunk_type = ChunkType.ASSESSMENT
    format_markers = ("nutrition assessment", "nutrition follow up")
