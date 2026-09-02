from __future__ import annotations

import importlib
import logging
import typing

from ntk.models.extracted_fact_create import KnowledgeChunkPayload
from ntk.models.knowledge import KnowledgeType
from ntk.models.sql.resident import (
    ExtractionStatus,
)
from ntk.services.embedding_service import EmbeddingService
from ntk.services.resident_data.extract.pcc_order_report import (
    OrderReportMode,
    PccOrderReportExtractor,
)
from ntk.services.resident_data.extract.registry import EXTRACTOR_REGISTRY
from ntk.services.resident_data.extract.unknown_file import UnknownFileExtractor
from ntk.services.resident_data.transform import (
    ExtractedFactTransformer,
    ResidentTransformationResult,
)

if typing.TYPE_CHECKING:
    import pathlib

    from ntk.models.extracted_fact_create import ExtractedFactCreate
    from ntk.models.sql.knowledge import Knowledge
    from ntk.repositories.knowledge_repo import KnowledgeRepo
    from ntk.repositories.progress_note_repo import ProgressNoteRepo
    from ntk.repositories.resident_repo import ResidentRepo
    from ntk.services.resident_data.extract.base import BaseExtractor
    from ntk.services.resident_data.extract.knowledge_extractor import (
        KnowledgeExtractor,
    )
    from ntk.services.resident_data.extract.pcc_progress_notes import (
        PccProgressNotesExtractor,
    )
    from ntk.services.resident_data.extract.wound_report import WoundReportExtractor
    from ntk.services.resident_data.resident_resolver import ResidentResolver
    from ntk.services.resident_data.transform import TransformedDocument

logger = logging.getLogger(__name__)

_EXTRACTOR_MODULES = (
    (
        "ntk.services.resident_data.extract.pcc_weight_history",
        "PccWeightHistoryExtractor",
    ),
    (
        "ntk.services.resident_data.extract.pcc_progress_notes",
        "PccProgressNotesExtractor",
    ),
    (
        "ntk.services.resident_data.extract.pcc_lab_results",
        "PccLabResultsExtractor",
    ),
    ("ntk.services.resident_data.extract.wound_report", "WoundReportExtractor"),
    (
        "ntk.services.resident_data.extract.pcc_order_report",
        "PccOrderReportExtractor",
    ),
    (
        "ntk.services.resident_data.extract.knowledge_extractor",
        "NutritionCareManualExtractor",
    ),
    (
        "ntk.services.resident_data.extract.knowledge_extractor",
        "DietManualExtractor",
    ),
)

_KNOWLEDGE_EXTRACTORS = {
    KnowledgeType.DIET_MANUAL: "DietManualExtractor",
    KnowledgeType.NUTRITION_CARE_MANUAL: "NutritionCareManualExtractor",
}

_FACT_TYPE_BY_EXTRACTOR: dict[str, str | None] = {
    "PccWeightHistoryExtractor": "weight",
    "PccProgressNotesExtractor": None,
    "PccLabResultsExtractor": "lab",
    "WoundReportExtractor": "wound",
    "PccOrderReportExtractor": "order",
    "UnknownFileExtractor": None,
}


def load_extractors() -> tuple[type[BaseExtractor], ...]:
    """Import and return supported extractors in detection order."""
    for module_name, _ in _EXTRACTOR_MODULES:
        importlib.import_module(module_name)
    try:
        return tuple(
            EXTRACTOR_REGISTRY[class_name] for _, class_name in _EXTRACTOR_MODULES
        )
    except KeyError as error:
        msg = f"Extractor '{error.args[0]}' did not register"
        raise RuntimeError(msg) from error


_EXTRACTORS = load_extractors()


class ResidentIngestionService:
    """ETL for Resident Data."""

    def __init__(
        self,
        knowledge_repository: KnowledgeRepo | None = None,
        progress_note_repository: ProgressNoteRepo | None = None,
        resident_resolver: ResidentResolver | None = None,
    ) -> None:
        """Initialize optional persistence and embedding dependencies."""
        self.knowledge_repository = knowledge_repository
        self.progress_note_repository = progress_note_repository
        self.resident_resolver = resident_resolver
        self.transformer: ExtractedFactTransformer | None = None
        self._extractor_cache: dict[pathlib.Path, BaseExtractor] = {}

    @staticmethod
    def _get_extractor(path: pathlib.Path) -> BaseExtractor:
        """Return the first extractor that recognizes the document.

        Returns None when no extractor found for current document.
        """
        ResidentIngestionService._validate_path(path)
        extractors = tuple(extractor_type(path) for extractor_type in _EXTRACTORS)
        for extractor in extractors:
            if extractor.is_expected_format():
                return extractor
        return UnknownFileExtractor(path)

    def _find_extractor(self, path: pathlib.Path) -> BaseExtractor:
        """Find extractor class for given file.

        :param path: full path to file
        :return: BaseExtractor or None if no extractor exists
        """
        resolved_path = path.resolve()
        if resolved_path not in self._extractor_cache:
            self._extractor_cache[resolved_path] = self._get_extractor(resolved_path)
        return self._extractor_cache[resolved_path]

    @classmethod
    def _find_knowledge_extractor(
        cls,
        path: pathlib.Path,
        knowledge_type: KnowledgeType,
    ) -> KnowledgeExtractor:
        """Return the extractor registered for the requested knowledge type."""
        cls._validate_path(path)
        extractor_name = _KNOWLEDGE_EXTRACTORS[knowledge_type]
        extractor = EXTRACTOR_REGISTRY[extractor_name](path)
        if not extractor.is_expected_format():
            msg = f"Document is not a {knowledge_type.value}: {path.name}"
            raise TypeError(msg)
        return typing.cast("KnowledgeExtractor", extractor)

    async def ingest(
        self,
        files: list[pathlib.Path],
    ) -> ResidentTransformationResult:
        """Extract and transform every resident document."""
        transformed_documents: list[TransformedDocument] = []
        active_order_documents: list[TransformedDocument] = []
        incremental_documents: list[TransformedDocument] = []
        ingested_files: list[pathlib.Path] = []
        request_checksums: set[str] = set()
        resident_repository = self._resident_repository()
        for path in files:
            checksum = ExtractedFactTransformer.document_checksum(path)
            if checksum in request_checksums or resident_repository.document_exists(
                checksum,
            ):
                logger.info("Skipping previously ingested document: %s", path)
                continue
            request_checksums.add(checksum)
            extracted_facts = await self._extract_report(path)
            transformed = self._fact_transformer().transform(
                path,
                extracted_facts,
                extractor_name=self._get_extractor_name(path),
            )
            transformed_documents.append(transformed)
            extractor = self._find_extractor(path)
            if (
                isinstance(extractor, PccOrderReportExtractor)
                and extractor.report_mode is OrderReportMode.ACTIVE_SNAPSHOT
            ):
                active_order_documents.append(transformed)
            else:
                incremental_documents.append(transformed)
            ingested_files.append(path)
        if incremental_documents:
            resident_repository.load_transformed_documents(incremental_documents)
        if active_order_documents:
            resident_repository.reconcile_active_order_documents(
                active_order_documents,
            )
        if transformed_documents:
            self._mark_progress_notes_extracted(ingested_files)
        return ResidentTransformationResult(documents=transformed_documents)

    def _mark_progress_notes_extracted(self, files: list[pathlib.Path]) -> None:
        """Mark successfully processed notes after their facts are persisted."""
        if self.progress_note_repository is None:
            return
        processed_notes = {
            note.note_key: note
            for path in files
            for note in getattr(
                self._find_extractor(path),
                "processed_progress_notes",
                (),
            )
        }
        for progress_note in processed_notes.values():
            self.progress_note_repository.set_extraction_status(
                progress_note,
                ExtractionStatus.EXTRACTED,
            )

    @staticmethod
    def _validate_fact_types(
        extractor_name: str,
        facts: list[ExtractedFactCreate],
    ) -> None:
        """Ensure an extractor returned only its declared fact type."""
        expected_fact_type = _FACT_TYPE_BY_EXTRACTOR[extractor_name]
        if expected_fact_type is None:
            return
        invalid_fact = next(
            (fact for fact in facts if fact.payload.type != expected_fact_type),
            None,
        )
        if invalid_fact is not None:
            msg = (
                f"{extractor_name} returned fact type "
                f"{invalid_fact.payload.type!r}; "
                f"expected {expected_fact_type!r}"
            )
            raise TypeError(msg)

    def _get_extractor_name(self, path: pathlib.Path) -> str:
        """Return the registered class name selected for a source path."""
        return type(self._find_extractor(path)).__name__

    async def _extract_report(
        self,
        path: pathlib.Path,
        *,
        resident_facility_id: str | None = None,
    ) -> list[ExtractedFactCreate]:
        """Extract normalized facts with a recognized resident extractor."""
        extractor = self._find_extractor(path)
        extractor_name = self._get_extractor_name(path)
        logger.debug("Using %s for data extraction", extractor_name)
        if extractor_name == "PccProgressNotesExtractor":
            if self.progress_note_repository is None:
                msg = "A progress-note repository is required for note ingestion"
                raise RuntimeError(msg)
            progress_extractor = typing.cast("PccProgressNotesExtractor", extractor)
            progress_extractor.progress_note_repository = self.progress_note_repository
            progress_extractor.resident_resolver = (
                self._resident_resolver().resolve_or_create_progress_note
            )
            facts = await progress_extractor.extract()
        elif extractor_name == "WoundReportExtractor":
            wound_extractor = typing.cast("WoundReportExtractor", extractor)
            facts = await wound_extractor.extract(facility_id=resident_facility_id)
        elif extractor_name == "UnknownFileExtractor":
            unknown_extractor = typing.cast("UnknownFileExtractor", extractor)
            unknown_extractor.resident_resolver = self._resident_resolver()
            facts = await unknown_extractor.extract()
        else:
            facts = await extractor.extract()
        self._validate_fact_types(extractor_name, facts)
        return facts

    async def ingest_knowledge(
        self,
        path: pathlib.Path,
        knowledge_type: KnowledgeType,
        *,
        overwrite: bool = False,
    ) -> Knowledge:
        """Chunk, embed, and persist one knowledge source."""
        knowledge_extractor = self._find_knowledge_extractor(path, knowledge_type)
        facts = await knowledge_extractor.extract()
        if facts is None:
            msg = "Knowledge chunk extraction is not implemented"
            raise NotImplementedError(msg)
        if not all(isinstance(fact.payload, KnowledgeChunkPayload) for fact in facts):
            msg = "Knowledge extractor returned an unsupported fact type"
            raise TypeError(msg)
        chunks = [
            typing.cast("KnowledgeChunkPayload", fact.payload).content for fact in facts
        ]
        repository = self._knowledge_repository()
        knowledge = knowledge_extractor.create_knowledge()
        existing = repository.find_existing_knowledge(
            knowledge_type,
            knowledge.file_hash,
        )
        if existing is not None and not overwrite:
            return existing
        embedding_service = self._embedding_service()
        embeddings = await embedding_service.get_embeddings_async(chunks)
        return repository.ingest(
            knowledge,
            chunks,
            embeddings,
            embedding_service.embedding_model,
            overwrite=overwrite,
        )

    @staticmethod
    def _validate_path(path: pathlib.Path) -> None:
        if not path.is_file():
            msg = f"Document file does not exist: {path}"
            raise ValueError(msg)

    def _knowledge_repository(self) -> KnowledgeRepo:
        if self.knowledge_repository is None:
            msg = "A knowledge repository is required for knowledge ingestion"
            raise RuntimeError(msg)
        return self.knowledge_repository

    def _resident_repository(self) -> ResidentRepo:
        return self._resident_resolver().resident_repository

    def _resident_resolver(self) -> ResidentResolver:
        if self.resident_resolver is None:
            msg = "A resident resolver is required for resident ingestion"
            raise RuntimeError(msg)
        return self.resident_resolver

    def _fact_transformer(self) -> ExtractedFactTransformer:
        """Return the configured transformer with resident ID resolution."""
        if self.transformer is None:
            self.transformer = ExtractedFactTransformer(self._resident_resolver())
        return self.transformer

    def _embedding_service(self) -> EmbeddingService:
        return EmbeddingService()
