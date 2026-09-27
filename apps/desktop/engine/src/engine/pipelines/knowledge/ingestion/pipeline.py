"""Ingest reusable nutrition knowledge documents."""

from __future__ import annotations

import typing

from engine.models.sql.knowledge import KnowledgeType

from .extractors import DietManualExtractor, NutritionCareManualExtractor
from .processing import KnowledgeContentProcessor

if typing.TYPE_CHECKING:
    import pathlib

    from engine.models.sql.knowledge import Knowledge
    from engine.repositories.knowledge_repo import KnowledgeRepo
    from engine.services.embedding_service import EmbeddingService

    from .extractors.base import KnowledgeExtractor

_EXTRACTORS_BY_TYPE = {
    KnowledgeType.DIET_MANUAL: DietManualExtractor,
    KnowledgeType.NUTRITION_CARE_MANUAL: NutritionCareManualExtractor,
}


class KnowledgeIngestionPipeline:
    """Extract, embed, and persist reusable nutrition knowledge."""

    def __init__(
        self,
        knowledge_repository: KnowledgeRepo,
        embedding_service: EmbeddingService,
        content_processor: KnowledgeContentProcessor | None = None,
    ) -> None:
        """Initialize knowledge persistence and embedding dependencies."""
        self.knowledge_repository = knowledge_repository
        self.embedding_service = embedding_service
        self.content_processor = content_processor or KnowledgeContentProcessor()

    @classmethod
    def _find_extractor(
        cls,
        path: pathlib.Path,
        knowledge_type: KnowledgeType,
    ) -> KnowledgeExtractor:
        """Return the extractor registered for the requested knowledge type."""
        cls._validate_path(path)
        extractor = _EXTRACTORS_BY_TYPE[knowledge_type](path)
        if not extractor.is_expected_format():
            msg = f"Document is not a {knowledge_type.value}: {path.name}"
            raise TypeError(msg)
        return extractor

    async def ingest_knowledge(
        self,
        path: pathlib.Path,
        knowledge_type: KnowledgeType,
        *,
        overwrite: bool = False,
    ) -> Knowledge:
        """Chunk, embed, and persist one knowledge source."""
        extractor = self._find_extractor(path, knowledge_type)
        pages = await extractor.extract()
        chunks = self.content_processor.build_chunks(pages)
        knowledge = extractor.create_knowledge()
        existing = self.knowledge_repository.find_existing_knowledge(
            knowledge_type,
            knowledge.file_hash,
        )
        if existing is not None and not overwrite:
            return existing
        embedding_text = [chunk.content for chunk in chunks]
        embeddings = await self.embedding_service.get_embeddings_async(embedding_text)
        return self.knowledge_repository.ingest(
            knowledge,
            chunks,
            embeddings,
            overwrite=overwrite,
        )

    @staticmethod
    def _validate_path(path: pathlib.Path) -> None:
        """Raise when the source document does not exist."""
        if not path.is_file():
            msg = f"Document file does not exist: {path}"
            raise ValueError(msg)


__all__ = ["KnowledgeIngestionPipeline"]
