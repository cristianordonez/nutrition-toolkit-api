"""Knowledge-ingestion specialization of the shared extractor contract."""

from __future__ import annotations

import typing
from hashlib import sha256

from ntk.models.knowledge import ExtractedKnowledgePage
from ntk.models.sql.knowledge import Knowledge
from ntk.pipelines.extraction import DocumentExtractor

if typing.TYPE_CHECKING:
    from ntk.models.knowledge import KnowledgeType


class KnowledgeExtractor(DocumentExtractor[list[ExtractedKnowledgePage]]):
    """Base class for reusable clinical knowledge document extractors."""

    knowledge_type: typing.ClassVar[KnowledgeType]

    async def extract(self) -> list[ExtractedKnowledgePage]:
        """Extract readable content while retaining one-based page provenance."""
        return [
            ExtractedKnowledgePage(page_number=page_number, text=text)
            for page_number, text in self._document_pages
            if text
        ]

    def create_knowledge(self) -> Knowledge:
        """Create the persisted identity for this knowledge source."""
        return Knowledge(
            filename=self.path.name,
            knowledge_type=self.knowledge_type,
            file_hash=sha256(self.path.read_bytes()).hexdigest(),
        )


__all__ = ["KnowledgeExtractor"]
