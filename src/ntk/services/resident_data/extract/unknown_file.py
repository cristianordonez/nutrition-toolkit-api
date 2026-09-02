"""Text extraction for documents without a deterministic extractor."""

from __future__ import annotations

import typing
from datetime import UTC, date, datetime, time

import pymupdf

from ntk.agents.data_extraction_agent import (
    DATA_EXTRACTION_MODEL,
    DataExtractionAgent,
    ExtractionInput,
)
from ntk.models.extracted_fact_create import ExtractedFactCreate
from ntk.services.resident_data.extract.base import BaseExtractor
from ntk.utils.tokens import sliding_window

if typing.TYPE_CHECKING:
    import pathlib

    from ntk.models.ai_extraction import (
        AIExtractedIdentity,
        AIUnknownDocumentFact,
    )
    from ntk.services.resident_data.resident_resolver import (
        ResidentResolution,
        ResidentResolver,
    )


_SUPPORTED_SUFFIXES = {".pdf"}
_UNKNOWN_DOCUMENT_CHUNK_TOKENS = 600
_MAX_UNKNOWN_FILE_SIZE_BYTES = 10 * 1024 * 1024


class UnknownFileTooLargeError(ValueError):
    """Raised before extraction when an unknown file exceeds the size limit."""


class UnknownFileUnsupportedFormatError(TypeError):
    """Raised before extraction when unknown file is unsupported format."""


class UnknownFileExtractor(BaseExtractor):
    """Read text from an unrecognized file of a supported file type."""

    def __init__(
        self,
        file: pathlib.Path,
        *,
        max_file_size_bytes: int = _MAX_UNKNOWN_FILE_SIZE_BYTES,
        resident_resolver: ResidentResolver | None = None,
    ) -> None:
        """Store the document to read."""
        if max_file_size_bytes <= 0:
            msg = "Unknown file size limit must be greater than zero"
            raise ValueError(msg)
        self.file = file
        self.max_file_size_bytes = max_file_size_bytes
        self.resident_resolver = resident_resolver
        self._validate_file_size()
        self._validate_file_type()

    def is_expected_format(self) -> bool:
        """Return true when file is supported for extraction."""
        self._validate_file_size()
        self._validate_file_type()
        return True

    async def extract(self) -> list[ExtractedFactCreate]:
        """Parse unstructured text using an extraction agent."""
        facts: list[ExtractedFactCreate] = []
        for source_page, page_text in self._get_document_pages():
            for chunk in sliding_window(
                page_text,
                chunk_size=_UNKNOWN_DOCUMENT_CHUNK_TOKENS,
                overlap=25,
            ):
                if not chunk.strip():
                    continue
                extracted_facts = await self._run_data_extraction_agent(
                    ExtractionInput(
                        text=chunk,
                        document_filename=self.file.name,
                    ),
                )
                facts.extend(
                    self._build_extracted_fact_create(fact, source_page)
                    for fact in extracted_facts
                )
        return facts

    def _validate_file_size(self) -> None:
        """Reject oversized files before reading content or calling the agent."""
        file_size = self.file.stat().st_size
        if file_size <= self.max_file_size_bytes:
            return
        max_size_mib = self.max_file_size_bytes / (1024 * 1024)
        actual_size_mib = file_size / (1024 * 1024)
        msg = (
            f"Unknown file '{self.file.name}' is too large for AI extraction "
            f"({actual_size_mib:.2f} MiB); maximum size is {max_size_mib:.2f} MiB"
        )
        raise UnknownFileTooLargeError(msg)

    def _validate_file_type(self) -> None:
        suffix = self.file.suffix.casefold()
        if suffix not in _SUPPORTED_SUFFIXES:
            msg = f"Unsupported file type for text extraction: {suffix or '<none>'}"
            raise UnknownFileUnsupportedFormatError(msg)

    async def _run_data_extraction_agent(
        self,
        extraction_input: ExtractionInput,
    ) -> list[AIUnknownDocumentFact]:
        """Run the agent and enforce its transient-fact result contract."""
        data_extraction_agent = DataExtractionAgent()
        return await data_extraction_agent.run_unknown_document(extraction_input)

    def _build_extracted_fact_create(
        self,
        extracted: AIUnknownDocumentFact,
        source_page: int | None,
    ) -> ExtractedFactCreate:
        """Combine an AI fact with its resolved resident identity."""
        identity = extracted.identity
        resolution = self._resolve_identity(
            identity,
            effective_at=self._effective_at(extracted),
        )
        return ExtractedFactCreate(
            payload=extracted.fact.payload,
            confidence=extracted.fact.confidence,
            confidence_reason=extracted.fact.confidence_reason,
            model_name=DATA_EXTRACTION_MODEL,
            facility_resident_identifier=identity.facility_resident_identifier,
            resident_name=identity.resident_name,
            facility_name=identity.facility_name,
            resident_id=resolution.resident_id if resolution is not None else None,
            facility_id=resolution.facility_id if resolution is not None else None,
            resident_facility_stay_id=(
                resolution.resident_facility_stay_id if resolution is not None else None
            ),
            source_page=source_page,
        )

    def _resolve_identity(
        self,
        identity: AIExtractedIdentity,
        *,
        effective_at: datetime | None,
    ) -> ResidentResolution | None:
        if self.resident_resolver is None:
            return None
        resolution = self.resident_resolver.resolve(
            facility_name=identity.facility_name,
            facility_resident_identifier=identity.facility_resident_identifier,
            resident_name=identity.resident_name,
            effective_at=effective_at,
        )
        if resolution is not None:
            return resolution
        if identity.facility_name and identity.resident_name:
            return self.resident_resolver.resolve_or_create_resident(
                facility_name=identity.facility_name,
                facility_resident_identifier=identity.facility_resident_identifier,
                resident_name=identity.resident_name,
                effective_at=effective_at,
            )
        return None

    @staticmethod
    def _effective_at(extracted: AIUnknownDocumentFact) -> datetime | None:
        payload = extracted.fact.payload
        for field_name in (
            "observed_at",
            "measured_at",
            "revision_date",
        ):
            value = getattr(payload, field_name, None)
            if isinstance(value, datetime):
                return value
            if isinstance(value, date):
                return datetime.combine(value, time.min, tzinfo=UTC)
        return None

    def _get_document_contents(self) -> str:
        """Return all readable text, retained for callers needing plain text."""
        return "\n".join(text for _, text in self._get_document_pages())

    def _get_document_pages(self) -> list[tuple[int | None, str]]:
        """Read text with one-based PDF page provenance when available."""
        with pymupdf.open(self.file) as document:
            return [
                (page_number + 1, document.load_page(page_number).get_text().strip())
                for page_number in range(document.page_count)
            ]
