from __future__ import annotations

import importlib
import logging
import typing

from engine.models.sql.clinical_source import (
    ClinicalSource,
    ClinicalSourceKind,
    ExtractionStatus,
    SourceAuthority,
)
from engine.utils.misc import require_id

from .extract.pcc_order_report import (
    OrderReportMode,
    PccOrderReportExtractor,
)
from .extract.pcc_progress_notes import (
    ParsedProgressNote,
    PccProgressNotesExtractor,
    PreparedProgressNoteExtraction,
)
from .extract.registry import EXTRACTOR_REGISTRY
from .extract.unknown_file import UnknownFileExtractor
from .transformer import (
    ClinicalFactTransformer,
    PersonTransformationResult,
)

if typing.TYPE_CHECKING:
    import pathlib
    from datetime import date

    from engine.models.extracted_fact_create import ExtractedFactCreate
    from engine.repositories.clinical_source_repo import ClinicalSourceRepo
    from engine.repositories.person_repo import PersonRepo
    from engine.services.person.person_service import PersonService

    from .extract.base import PersonExtractor
    from .extract.wound_report import WoundReportExtractor
    from .transformer import TransformedDocument

logger = logging.getLogger(__name__)

_EXTRACTOR_MODULES = (
    (
        "engine.pipelines.person.ingestion.extract.pcc_weight_history",
        "PccWeightHistoryExtractor",
    ),
    (
        "engine.pipelines.person.ingestion.extract.pcc_progress_notes",
        "PccProgressNotesExtractor",
    ),
    (
        "engine.pipelines.person.ingestion.extract.pcc_lab_results",
        "PccLabResultsExtractor",
    ),
    ("engine.pipelines.person.ingestion.extract.wound_report", "WoundReportExtractor"),
    (
        "engine.pipelines.person.ingestion.extract.pcc_order_report",
        "PccOrderReportExtractor",
    ),
)

_FACT_TYPE_BY_EXTRACTOR: dict[str, str | None] = {
    "PccWeightHistoryExtractor": "weight",
    "PccProgressNotesExtractor": None,
    "PccLabResultsExtractor": "lab",
    "WoundReportExtractor": "wound",
    "PccOrderReportExtractor": None,
    "UnknownFileExtractor": None,
}


def load_extractors() -> tuple[type[PersonExtractor], ...]:
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


def _validate_document_path(path: pathlib.Path) -> None:
    """Require one existing document file."""
    if not path.is_file():
        msg = f"Document file does not exist: {path}"
        raise ValueError(msg)


def get_person_extractor(path: pathlib.Path) -> PersonExtractor:
    """Return the first extractor that recognizes one person document."""
    _validate_document_path(path)
    extractors = tuple(extractor_type(path) for extractor_type in _EXTRACTORS)
    for extractor in extractors:
        if extractor.is_expected_format():
            return extractor
    return UnknownFileExtractor(path)


class PersonIngestionPipeline:
    """ETL for Person Data."""

    def __init__(
        self,
        clinical_source_repository: ClinicalSourceRepo | None = None,
        person_service: PersonService | None = None,
    ) -> None:
        """Initialize optional persistence and embedding dependencies."""
        self.clinical_source_repository = clinical_source_repository
        self.person_service = person_service
        self.transformer: ClinicalFactTransformer | None = None
        self._extractor_cache: dict[pathlib.Path, PersonExtractor] = {}
        self._processed_clinical_sources: dict[
            pathlib.Path,
            list[ClinicalSource],
        ] = {}

    @staticmethod
    def _get_extractor(path: pathlib.Path) -> PersonExtractor:
        """Return the recognized extractor for compatibility callers."""
        return get_person_extractor(path)

    def _find_extractor(self, path: pathlib.Path) -> PersonExtractor:
        """Find extractor class for given file.

        :param path: full path to file
        :return: the matching person extractor
        """
        resolved_path = path.resolve()
        if resolved_path not in self._extractor_cache:
            self._extractor_cache[resolved_path] = self._get_extractor(resolved_path)
        return self._extractor_cache[resolved_path]

    async def ingest(
        self,
        files: list[pathlib.Path],
        *,
        person_id: int | None = None,
        source_person_name: str | None = None,
        date_of_birth: date | None = None,
    ) -> PersonTransformationResult:
        """Extract and transform every person document.

        `person_id`, `source_person_name`, and `date_of_birth` pin an unknown
        (non-deterministically-recognized) document to an already-identified
        resident, such as a person-scoped upload; they are ignored by
        extractors that resolve identity from structured source data.
        """
        transformed_documents: list[TransformedDocument] = []
        active_order_documents: list[TransformedDocument] = []
        incremental_documents: list[TransformedDocument] = []
        ingested_files: list[pathlib.Path] = []
        request_checksums: set[str] = set()
        person_repository = self._person_repository()
        for path in files:
            checksum = ClinicalFactTransformer.document_checksum(path)
            if checksum in request_checksums:
                logger.info("Skipping duplicate file in this request: %s", path)
                continue
            # Skip only what finished. A genuine extraction error leaves a
            # FAILED source and is retried; a successful zero-fact result is
            # recorded as NOT_APPLICABLE and is complete.
            if person_repository.document_ingestion_is_complete(checksum):
                logger.info("Skipping previously ingested document: %s", path)
                continue
            if person_repository.document_exists(checksum):
                logger.info(
                    "Re-processing %s: it was ingested before but has unfinished "
                    "or failed extraction",
                    path,
                )
            request_checksums.add(checksum)
            extractor = self._find_extractor(path)
            extracted_facts = await self._extract_report(
                path,
                person_id=person_id,
                source_person_name=source_person_name,
                date_of_birth=date_of_birth,
            )
            extracted_facts = self._filter_source_owned_facts(
                extractor,
                extracted_facts,
            )
            transformed = self._fact_transformer().transform(
                path,
                extracted_facts,
                extractor_name=self._get_extractor_name(path),
                source_observed_at=getattr(
                    extractor,
                    "source_observed_at",
                    None,
                ),
                existing_sources=self._processed_clinical_sources.get(
                    path.resolve(),
                    (),
                ),
            )
            transformed_documents.append(transformed)
            if (
                isinstance(extractor, PccOrderReportExtractor)
                and extractor.report_mode is OrderReportMode.ACTIVE_SNAPSHOT
            ):
                active_order_documents.append(transformed)
            else:
                incremental_documents.append(transformed)
            ingested_files.append(path)
        if incremental_documents:
            person_repository.load_transformed_documents(incremental_documents)
        if active_order_documents:
            person_repository.reconcile_active_order_documents(
                active_order_documents,
            )
        if transformed_documents:
            self._mark_clinical_sources_extracted(ingested_files)
        return PersonTransformationResult(documents=transformed_documents)

    @staticmethod
    def _filter_source_owned_facts(
        extractor: PersonExtractor,
        facts: list[ExtractedFactCreate],
    ) -> list[ExtractedFactCreate]:
        """Keep the current diet owned exclusively by structured order reports."""
        if isinstance(extractor, PccOrderReportExtractor):
            return facts
        return [fact for fact in facts if fact.payload.type != "diet"]

    def _mark_clinical_sources_extracted(self, files: list[pathlib.Path]) -> None:
        """Mark successfully processed notes after their facts are persisted."""
        if self.clinical_source_repository is None:
            return
        processed_sources = {
            source.source_key: source
            for path in files
            for source in self._processed_clinical_sources.pop(path.resolve(), ())
        }
        for source in processed_sources.values():
            if source.extraction_status is ExtractionStatus.FAILED:
                continue
            self.clinical_source_repository.set_extraction_status(
                source,
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
        source_person_identifier: str | None = None,
        person_id: int | None = None,
        source_person_name: str | None = None,
        date_of_birth: date | None = None,
    ) -> list[ExtractedFactCreate]:
        """Extract normalized facts with a recognized person extractor."""
        extractor = self._find_extractor(path)
        extractor_name = self._get_extractor_name(path)
        logger.debug("Using %s for data extraction", extractor_name)
        if extractor_name == "PccProgressNotesExtractor":
            progress_extractor = typing.cast("PccProgressNotesExtractor", extractor)
            facts = await self._extract_clinical_notes(path, progress_extractor)
        elif extractor_name == "WoundReportExtractor":
            wound_extractor = typing.cast("WoundReportExtractor", extractor)
            facts = await wound_extractor.extract(
                source_person_identifier=source_person_identifier,
            )
        elif extractor_name == "UnknownFileExtractor":
            unknown_extractor = typing.cast("UnknownFileExtractor", extractor)
            facts = await unknown_extractor.extract(
                person_id=person_id,
                known_person_name=source_person_name,
                known_date_of_birth=date_of_birth,
            )
        else:
            facts = await extractor.extract()
        self._validate_fact_types(extractor_name, facts)
        return facts

    async def _extract_clinical_notes(
        self,
        path: pathlib.Path,
        extractor: PccProgressNotesExtractor,
    ) -> list[ExtractedFactCreate]:
        """Resolve and persist notes before persistence-free fact extraction."""
        repository = self._clinical_source_repository()
        prepared: list[PreparedProgressNoteExtraction] = []
        source_by_key: dict[str, ClinicalSource] = {}
        selected_notes = extractor.extract_notes()
        selected_identities = {
            (note.source_person_identifier, note.source_person_name)
            for note in selected_notes
        }
        for identity_note in extractor.report_identity_notes():
            identity = (
                identity_note.source_person_identifier,
                identity_note.source_person_name,
            )
            if identity not in selected_identities:
                self._person_service().resolve_or_create_clinical_note(identity_note)
        for note_key, note in extractor.deduplicate_notes(selected_notes):
            clinical_source = self._prepare_clinical_source(note, note_key)
            if clinical_source is None:
                continue
            source_by_key[note_key] = clinical_source
            prepared.append(
                PreparedProgressNoteExtraction(
                    note=note,
                    person_id=clinical_source.person_id,
                    clinical_source_id=clinical_source.id,
                ),
            )
        facts = extractor.extract_header_facts()
        for outcome in await extractor.extract_prepared(prepared):
            note_key = extractor.get_note_key(
                source_person_identifier=outcome.prepared.note.source_person_identifier,
                effective_at=outcome.prepared.note.note_date,
                note_type=outcome.prepared.note.note_type,
                author=outcome.prepared.note.author,
                note_text=outcome.prepared.note.note_text,
            )
            clinical_source = source_by_key[note_key]
            if outcome.error is not None:
                repository.set_extraction_status(
                    clinical_source,
                    ExtractionStatus.FAILED,
                )
                continue
            facts.extend(outcome.facts or ())
        self._processed_clinical_sources[path.resolve()] = list(  # noqa: ASYNC240
            source_by_key.values(),
        )
        return facts

    def _prepare_clinical_source(
        self,
        note: ParsedProgressNote,
        note_key: str,
    ) -> ClinicalSource | None:
        """Resolve identity and create or prepare one persisted clinical note."""
        repository = self._clinical_source_repository()
        person = self._person_service().resolve_or_create_clinical_note(note)
        existing = repository.get_by_key(note_key)
        if existing is not None:
            existing = repository.update_identity(
                existing,
                person_id=require_id(person.id),
            )
            if existing.extraction_status is ExtractionStatus.FAILED:
                repository.set_extraction_status(existing, ExtractionStatus.PENDING)
            if existing.extraction_status in {
                ExtractionStatus.EXTRACTED,
                ExtractionStatus.SKIPPED,
            }:
                logger.debug(
                    "Skipping completed clinical note %s with status %s",
                    note_key,
                    existing.extraction_status,
                )
                return None
            return existing
        if note.note_date is None:
            msg = f"Clinical note {note_key} does not have an effective date"
            raise ValueError(msg)
        return repository.create(
            ClinicalSource(
                person_id=require_id(person.id),
                source_kind=ClinicalSourceKind.PROGRESS_NOTE,
                source_key=note_key,
                effective_at=note.note_date,
                note_type=note.note_type,
                author=note.author,
                content=note.note_text,
                raw_content=note.raw_text,
                content_hash=ClinicalFactTransformer.content_hash(note.raw_text),
                page_start=note.source_page,
                page_end=note.source_page,
                locator={"page": note.source_page}
                if note.source_page is not None
                else {},
                source_system="pointclickcare",
                source_record_type=note.note_type,
                source_authority=SourceAuthority.CLINICAL_DOCUMENT,
                extraction_status=ExtractionStatus.PENDING,
            ),
        )

    @staticmethod
    def _validate_path(path: pathlib.Path) -> None:
        _validate_document_path(path)

    def _person_repository(self) -> PersonRepo:
        return self._person_service().repository

    def _clinical_source_repository(self) -> ClinicalSourceRepo:
        if self.clinical_source_repository is None:
            msg = "A clinical-source repository is required for note ingestion"
            raise RuntimeError(msg)
        return self.clinical_source_repository

    def _person_service(self) -> PersonService:
        if self.person_service is None:
            msg = "A person service is required for person ingestion"
            raise RuntimeError(msg)
        return self.person_service

    def _fact_transformer(self) -> ClinicalFactTransformer:
        """Return the configured transformer with person ID resolution."""
        if self.transformer is None:
            self.transformer = ClinicalFactTransformer(self._person_service())
        return self.transformer
