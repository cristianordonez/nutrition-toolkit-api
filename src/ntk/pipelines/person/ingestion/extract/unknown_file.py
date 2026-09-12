"""Text extraction for documents without a deterministic extractor."""

from __future__ import annotations

import typing

import pymupdf

from ntk.agents.data_extraction_agent import (
    DATA_EXTRACTION_MODEL,
    DataExtractionAgent,
    ExtractionInput,
)
from ntk.models.extracted_fact_create import ExtractedFactCreate
from ntk.models.sql.extracted_fact import ExtractionMethod
from ntk.utils.tokens import sliding_window

from .base import PersonExtractor

if typing.TYPE_CHECKING:
    import pathlib

    from ntk.models.ai_extraction import AIUnknownDocumentFact


_SUPPORTED_SUFFIXES = {".pdf"}
_UNKNOWN_DOCUMENT_CHUNK_TOKENS = 600
_MAX_UNKNOWN_FILE_SIZE_BYTES = 10 * 1024 * 1024


class UnknownFileTooLargeError(ValueError):
    """Raised before extraction when an unknown file exceeds the size limit."""


class UnknownFileUnsupportedFormatError(TypeError):
    """Raised before extraction when unknown file is unsupported format."""


class UnknownFileExtractor(PersonExtractor):
    """Read text from an unrecognized file of a supported file type."""

    def __init__(
        self,
        file: pathlib.Path,
        *,
        max_file_size_bytes: int = _MAX_UNKNOWN_FILE_SIZE_BYTES,
    ) -> None:
        """Store the document to read."""
        super().__init__(file)
        if max_file_size_bytes <= 0:
            msg = "Unknown file size limit must be greater than zero"
            raise ValueError(msg)
        self.file = file
        self.max_file_size_bytes = max_file_size_bytes
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
        """Convert an AI fact while preserving its unresolved identity clues."""
        identity = extracted.identity
        return ExtractedFactCreate(
            payload=extracted.fact.payload,
            confidence=extracted.fact.confidence,
            confidence_reason=extracted.fact.confidence_reason,
            model_name=DATA_EXTRACTION_MODEL,
            extraction_method=ExtractionMethod.AI,
            source_person_identifier=identity.source_person_identifier,
            source_person_name=identity.source_person_name,
            facility_name=identity.facility_name,
            facility_identifier=identity.facility_identifier,
            source_page=source_page,
        )

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
