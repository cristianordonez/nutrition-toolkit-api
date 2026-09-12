"""Ingest reusable nutrition knowledge documents."""

from __future__ import annotations

import importlib
import typing

from ntk.models.knowledge import KnowledgeType
from ntk.services.embedding_service import EmbeddingService

from .extractors.registry import EXTRACTOR_REGISTRY
from .processing import KnowledgeContentProcessor

if typing.TYPE_CHECKING:
    import pathlib

    from ntk.models.sql.knowledge import Knowledge
    from ntk.repositories.knowledge_repo import KnowledgeRepo

    from .extractors.base import KnowledgeExtractor

_EXTRACTOR_MODULE = "ntk.pipelines.knowledge.ingestion.extractors.knowledge_extractor"
_EXTRACTOR_NAME_BY_TYPE = {
    KnowledgeType.DIET_MANUAL: "DietManualExtractor",
    KnowledgeType.NUTRITION_CARE_MANUAL: "NutritionCareManualExtractor",
}


def load_extractors() -> dict[KnowledgeType, type[KnowledgeExtractor]]:
    """Import and return the extractor registered for each knowledge type."""
    importlib.import_module(_EXTRACTOR_MODULE)
    try:
        return {
            knowledge_type: EXTRACTOR_REGISTRY[class_name]
            for knowledge_type, class_name in _EXTRACTOR_NAME_BY_TYPE.items()
        }
    except KeyError as error:
        msg = f"Extractor '{error.args[0]}' did not register"
        raise RuntimeError(msg) from error


_EXTRACTORS_BY_TYPE = load_extractors()


class KnowledgeIngestionPipeline:
    """Extract, embed, and persist reusable nutrition knowledge."""

    def __init__(
        self,
        knowledge_repository: KnowledgeRepo,
        embedding_service: EmbeddingService | None = None,
        content_processor: KnowledgeContentProcessor | None = None,
    ) -> None:
        """Initialize knowledge persistence and embedding dependencies."""
        self.knowledge_repository = knowledge_repository
        self.embedding_service = embedding_service or EmbeddingService()
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
            self.embedding_service.embedding_model,
            overwrite=overwrite,
        )

    @staticmethod
    def _validate_path(path: pathlib.Path) -> None:
        """Raise when the source document does not exist."""
        if not path.is_file():
            msg = f"Document file does not exist: {path}"
            raise ValueError(msg)


__all__ = ["KnowledgeIngestionPipeline", "load_extractors"]
