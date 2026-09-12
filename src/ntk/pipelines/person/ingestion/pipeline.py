from __future__ import annotations

import importlib
import logging
import typing

from ntk.models.sql.person import (
    ExtractionStatus,
    PersonProgressNote,
)
from ntk.utils.misc import require_id

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
    ExtractedFactTransformer,
    PersonTransformationResult,
)

if typing.TYPE_CHECKING:
    import pathlib

    from ntk.models.extracted_fact_create import ExtractedFactCreate
    from ntk.repositories.person_repo import PersonRepo
    from ntk.repositories.progress_note_repo import ProgressNoteRepo
    from ntk.services.facility_resolver import FacilityResolver
    from ntk.services.person.person_service import PersonService

    from .extract.base import PersonExtractor
    from .extract.wound_report import WoundReportExtractor
    from .transformer import TransformedDocument

logger = logging.getLogger(__name__)

_EXTRACTOR_MODULES = (
    (
        "ntk.pipelines.person.ingestion.extract.pcc_weight_history",
        "PccWeightHistoryExtractor",
    ),
    (
        "ntk.pipelines.person.ingestion.extract.pcc_progress_notes",
        "PccProgressNotesExtractor",
    ),
    (
        "ntk.pipelines.person.ingestion.extract.pcc_lab_results",
        "PccLabResultsExtractor",
    ),
    ("ntk.pipelines.person.ingestion.extract.wound_report", "WoundReportExtractor"),
    (
        "ntk.pipelines.person.ingestion.extract.pcc_order_report",
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
        progress_note_repository: ProgressNoteRepo | None = None,
        person_service: PersonService | None = None,
        facility_resolver: FacilityResolver | None = None,
    ) -> None:
        """Initialize optional persistence and embedding dependencies."""
        self.progress_note_repository = progress_note_repository
        self.person_service = person_service
        self.facility_resolver = facility_resolver
        self.transformer: ExtractedFactTransformer | None = None
        self._extractor_cache: dict[pathlib.Path, PersonExtractor] = {}
        self._processed_progress_notes: dict[
            pathlib.Path,
            list[PersonProgressNote],
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
    ) -> PersonTransformationResult:
        """Extract and transform every person document."""
        transformed_documents: list[TransformedDocument] = []
        active_order_documents: list[TransformedDocument] = []
        incremental_documents: list[TransformedDocument] = []
        ingested_files: list[pathlib.Path] = []
        request_checksums: set[str] = set()
        person_repository = self._person_repository()
        for path in files:
            checksum = ExtractedFactTransformer.document_checksum(path)
            if checksum in request_checksums or person_repository.document_exists(
                checksum,
            ):
                logger.info("Skipping previously ingested document: %s", path)
                continue
            request_checksums.add(checksum)
            extractor = self._find_extractor(path)
            extracted_facts = await self._extract_report(path)
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
            )
            transformed_documents.append(transformed)
            if (
                isinstance(extractor, PccOrderReportExtractor)
                and extractor.report_mode is OrderReportMode.ACTIVE_SNAPSHOT
                and all(
                    fact.facility_id is not None for fact in transformed.extracted_facts
                )
            ):
                active_order_documents.append(transformed)
            else:
                if (
                    isinstance(extractor, PccOrderReportExtractor)
                    and extractor.report_mode is OrderReportMode.ACTIVE_SNAPSHOT
                ):
                    logger.warning(
                        "Persisting %s without destructive order reconciliation "
                        "because its facility was not resolved",
                        path.name,
                    )
                incremental_documents.append(transformed)
            ingested_files.append(path)
        if incremental_documents:
            person_repository.load_transformed_documents(incremental_documents)
        if active_order_documents:
            person_repository.reconcile_active_order_documents(
                active_order_documents,
            )
        if transformed_documents:
            self._mark_progress_notes_extracted(ingested_files)
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

    def _mark_progress_notes_extracted(self, files: list[pathlib.Path]) -> None:
        """Mark successfully processed notes after their facts are persisted."""
        if self.progress_note_repository is None:
            return
        processed_notes = {
            note.note_key: note
            for path in files
            for note in self._processed_progress_notes.pop(path.resolve(), ())
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
        source_person_identifier: str | None = None,
    ) -> list[ExtractedFactCreate]:
        """Extract normalized facts with a recognized person extractor."""
        extractor = self._find_extractor(path)
        extractor_name = self._get_extractor_name(path)
        logger.debug("Using %s for data extraction", extractor_name)
        if extractor_name == "PccProgressNotesExtractor":
            progress_extractor = typing.cast("PccProgressNotesExtractor", extractor)
            facts = await self._extract_progress_notes(path, progress_extractor)
        elif extractor_name == "WoundReportExtractor":
            wound_extractor = typing.cast("WoundReportExtractor", extractor)
            facts = await wound_extractor.extract(
                source_person_identifier=source_person_identifier,
            )
        elif extractor_name == "UnknownFileExtractor":
            facts = await extractor.extract()
        else:
            facts = await extractor.extract()
        self._validate_fact_types(extractor_name, facts)
        return facts

    async def _extract_progress_notes(
        self,
        path: pathlib.Path,
        extractor: PccProgressNotesExtractor,
    ) -> list[ExtractedFactCreate]:
        """Resolve and persist notes before persistence-free fact extraction."""
        repository = self._progress_note_repository()
        prepared: list[PreparedProgressNoteExtraction] = []
        note_by_key: dict[str, PersonProgressNote] = {}
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
                self._person_service().resolve_or_create_progress_note(identity_note)
        for note_key, note in extractor.deduplicate_notes(selected_notes):
            progress_note = self._prepare_progress_note(note, note_key)
            if progress_note is None:
                continue
            note_by_key[note_key] = progress_note
            prepared.append(
                PreparedProgressNoteExtraction(
                    note=note,
                    person_id=progress_note.person_id,
                    progress_note_id=progress_note.id,
                ),
            )
        facts = extractor.extract_header_facts()
        successful_notes: list[PersonProgressNote] = []
        for outcome in await extractor.extract_prepared(prepared):
            note_key = extractor.get_note_key(
                source_person_identifier=outcome.prepared.note.source_person_identifier,
                effective_at=outcome.prepared.note.note_date,
                note_type=outcome.prepared.note.note_type,
                author=outcome.prepared.note.author,
                note_text=outcome.prepared.note.note_text,
            )
            progress_note = note_by_key[note_key]
            if outcome.error is not None:
                repository.set_extraction_status(
                    progress_note,
                    ExtractionStatus.FAILED,
                )
                continue
            facts.extend(outcome.facts or ())
            successful_notes.append(progress_note)
        self._processed_progress_notes[path.resolve()] = successful_notes  # noqa: ASYNC240
        return facts

    def _prepare_progress_note(
        self,
        note: ParsedProgressNote,
        note_key: str,
    ) -> PersonProgressNote | None:
        """Resolve identity and create or prepare one persisted progress note."""
        repository = self._progress_note_repository()
        person = self._person_service().resolve_or_create_progress_note(note)
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
                    "Skipping completed progress note %s with status %s",
                    note_key,
                    existing.extraction_status,
                )
                return None
            return existing
        if note.note_date is None:
            msg = f"Progress note {note_key} does not have an effective date"
            raise ValueError(msg)
        return repository.create(
            PersonProgressNote(
                person_id=require_id(person.id),
                note_date=note.note_date,
                note_type=note.note_type,
                author=note.author,
                note_text=note.note_text,
                raw_text=note.raw_text,
                note_key=note_key,
                extraction_status=ExtractionStatus.PENDING,
            ),
        )

    @staticmethod
    def _validate_path(path: pathlib.Path) -> None:
        _validate_document_path(path)

    def _person_repository(self) -> PersonRepo:
        return self._person_service().repository

    def _progress_note_repository(self) -> ProgressNoteRepo:
        if self.progress_note_repository is None:
            msg = "A progress-note repository is required for note ingestion"
            raise RuntimeError(msg)
        return self.progress_note_repository

    def _person_service(self) -> PersonService:
        if self.person_service is None:
            msg = "A person service is required for person ingestion"
            raise RuntimeError(msg)
        return self.person_service

    def _fact_transformer(self) -> ExtractedFactTransformer:
        """Return the configured transformer with person ID resolution."""
        if self.transformer is None:
            self.transformer = ExtractedFactTransformer(
                self._person_service(),
                self.facility_resolver,
            )
        return self.transformer
