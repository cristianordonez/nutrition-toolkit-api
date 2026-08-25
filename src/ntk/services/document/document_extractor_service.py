from __future__ import annotations

import importlib
import logging
import typing
from hashlib import sha256

from ntk.models.knowledge import KnowledgeType
from ntk.models.sql.assessment import Assessment, AssessmentSource
from ntk.services.open_ai_service import OpenAIService

from .extractors.registry import EXTRACTOR_REGISTRY

if typing.TYPE_CHECKING:
    import pathlib

    from ntk.models.sql.knowledge import Knowledge
    from ntk.models.sql.resident import ProgressNote
    from ntk.repositories.assessment_repo import AssessmentRepo
    from ntk.repositories.knowledge_repo import KnowledgeRepo

    from .extractors.base import BaseExtractor
    from .extractors.knowledge_extractor import KnowledgeExtractor
    from .extractors.pcc_progress_notes import PccProgressNotesExtractor
    from .extractors.wound_report import WoundReportExtractor

logger = logging.getLogger(__name__)

_EXTRACTOR_MODULES = (
    (
        "ntk.services.document.extractors.pcc_weight_history",
        "PccWeightHistoryExtractor",
    ),
    (
        "ntk.services.document.extractors.pcc_progress_notes",
        "PccProgressNotesExtractor",
    ),
    (
        "ntk.services.document.extractors.pcc_lab_results",
        "PccLabResultsExtractor",
    ),
    ("ntk.services.document.extractors.wound_report", "WoundReportExtractor"),
    (
        "ntk.services.document.extractors.pcc_order_report",
        "PccOrderReportExtractor",
    ),
    (
        "ntk.services.document.extractors.knowledge_extractor",
        "NutritionCareManualExtractor",
    ),
    (
        "ntk.services.document.extractors.knowledge_extractor",
        "DietManualExtractor",
    ),
)

_KNOWLEDGE_EXTRACTORS = {
    KnowledgeType.DIET_MANUAL: "DietManualExtractor",
    KnowledgeType.NUTRITION_CARE_MANUAL: "NutritionCareManualExtractor",
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


class DocumentExtractorService:
    """Select extractors and coordinate extracted document persistence."""

    def __init__(
        self,
        assessment_repository: AssessmentRepo | None = None,
        knowledge_repository: KnowledgeRepo | None = None,
        open_ai_service: OpenAIService | None = None,
    ) -> None:
        """Initialize optional persistence and embedding dependencies."""
        self.assessment_repository = assessment_repository
        self.knowledge_repository = knowledge_repository
        self.open_ai_service = open_ai_service
        self.extractors = load_extractors()
        self._extractor_cache: dict[pathlib.Path, BaseExtractor | None] = {}

    def _find_extractor(self, path: pathlib.Path) -> BaseExtractor | None:
        """Return the first extractor that recognizes the document.

        Returns None when no extractor found for current document.
        """
        self._validate_path(path)
        extractors = tuple(extractor_type(path) for extractor_type in self.extractors)
        for extractor in extractors:
            if extractor.is_expected_format():
                return extractor
        return None

    @classmethod
    def find_extractor(cls, path: pathlib.Path) -> BaseExtractor | None:
        """Return the first registered extractor that recognizes the document."""
        return cls().get_extractor(path)

    @classmethod
    def find_knowledge_extractor(
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

    def get_extractor(self, path: pathlib.Path) -> BaseExtractor | None:
        """Return and cache the recognized extractor for one source path."""
        resolved_path = path.resolve()
        if resolved_path not in self._extractor_cache:
            self._extractor_cache[resolved_path] = self._find_extractor(resolved_path)
        return self._extractor_cache[resolved_path]

    def get_extractor_name(self, path: pathlib.Path) -> str:
        """Return the registered class name selected for a source path."""
        return type(self.get_extractor(path)).__name__

    def extract_file(
        self,
        path: pathlib.Path,
        *,
        expected_extractor: str | None = None,
        resident_facility_id: str | None = None,
    ) -> object:
        """Extract file data with its recognized extractor."""
        extractor = self.get_extractor(path)
        if extractor is None:
            msg = f"No extractor found for {path}"
            raise TypeError(msg)
        extractor_name = type(extractor).__name__
        if expected_extractor is not None and extractor_name != expected_extractor:
            msg = (
                f"Expected {expected_extractor} for {path.name}, found {extractor_name}"
            )
            raise TypeError(msg)
        if extractor_name == "WoundReportExtractor":
            wound_extractor = typing.cast("WoundReportExtractor", extractor)
            return wound_extractor.extract(facility_id=resident_facility_id)
        return extractor.extract()

    def ingest_assessment(
        self,
        path: pathlib.Path,
        *,
        assessment_source: AssessmentSource = AssessmentSource.UPLOADED,
        created_by: str = "self",
        overwrite: bool = False,
    ) -> list[Assessment]:
        """Chunk, embed, and persist assessments from PCC progress notes."""
        notes = self.get_progress_notes_from_report(path)
        assessments = [
            self.create_assessment_from_progress_note(
                note,
                assessment_index=index,
                assessment_source=assessment_source,
                created_by=created_by,
            )
            for index, note in enumerate(notes)
        ]
        open_ai_service = self._open_ai_service()
        repo = self._assessment_repository()
        embeddings = [
            open_ai_service.get_embedding(assessment.content)
            for assessment in assessments
        ]
        return repo.ingest(
            assessments,
            embeddings,
            open_ai_service.embedding_model,
            overwrite=overwrite,
        )

    def get_progress_notes_from_report(self, path: pathlib.Path) -> list[ProgressNote]:
        """Extract normalized progress notes from a recognized PCC report."""
        load_extractors()
        extractor = EXTRACTOR_REGISTRY["PccProgressNotesExtractor"](path)
        if extractor.is_expected_format() is False:
            msg = f"Document is not a PCC progress notes report: {path.name}"
            raise TypeError(msg)
        progress_extractor = typing.cast("PccProgressNotesExtractor", extractor)
        return progress_extractor.extract().progress_notes

    @staticmethod
    def create_assessment_from_progress_note(
        note: ProgressNote,
        *,
        assessment_index: int = 0,
        assessment_source: AssessmentSource = AssessmentSource.UPLOADED,
        created_by: str | None = None,
    ) -> Assessment:
        """Convert one normalized progress note into a persisted assessment."""
        content = note.note_text.strip()
        if not content:
            msg = "Progress note text cannot be empty"
            raise ValueError(msg)
        creator = created_by.strip() if created_by is not None else ""
        if not creator and note.author:
            creator = note.author.strip()
        if not creator:
            creator = "unknown"
        normalized_content = " ".join(content.split())
        return Assessment(
            content=content,
            source=assessment_source,
            source_filename=note.source.source,
            content_hash=sha256(normalized_content.encode()).hexdigest(),
            assessment_index=assessment_index,
            assessment_date=note.note_date.date() if note.note_date else None,
            created_by=creator,
        )

    def ingest_knowledge(
        self,
        path: pathlib.Path,
        knowledge_type: KnowledgeType,
        *,
        overwrite: bool = False,
    ) -> Knowledge:
        """Chunk, embed, and persist one knowledge source."""
        knowledge_extractor = self.find_knowledge_extractor(path, knowledge_type)
        chunks = knowledge_extractor.extract()
        if chunks is None:
            msg = "Knowledge chunk extraction is not implemented"
            raise NotImplementedError(msg)
        repository = self._knowledge_repository()
        knowledge = knowledge_extractor.create_knowledge()
        existing = repository.find_existing_knowledge(
            knowledge_type,
            knowledge.file_hash,
        )
        if existing is not None and not overwrite:
            return existing
        open_ai_service = self._open_ai_service()
        embeddings = [open_ai_service.get_embedding(chunk) for chunk in chunks]
        return repository.ingest(
            knowledge,
            chunks,
            embeddings,
            self._open_ai_service().embedding_model,
            overwrite=overwrite,
        )

    @staticmethod
    def _validate_path(path: pathlib.Path) -> None:
        if not path.is_file():
            msg = f"Document file does not exist: {path}"
            raise ValueError(msg)

    def _assessment_repository(self) -> AssessmentRepo:
        if self.assessment_repository is None:
            msg = "An assessment repository is required for assessment ingestion"
            raise RuntimeError(msg)
        return self.assessment_repository

    def _knowledge_repository(self) -> KnowledgeRepo:
        if self.knowledge_repository is None:
            msg = "A knowledge repository is required for knowledge ingestion"
            raise RuntimeError(msg)
        return self.knowledge_repository

    def _open_ai_service(self) -> OpenAIService:
        if self.open_ai_service is None:
            self.open_ai_service = OpenAIService()
        return self.open_ai_service
