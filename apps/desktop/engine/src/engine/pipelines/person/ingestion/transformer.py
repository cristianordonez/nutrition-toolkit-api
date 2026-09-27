"""Transform validated extraction results into generic clinical persistence."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import typing

import pymupdf
from pydantic import BaseModel, ConfigDict

from engine.models.clinical_fact_registry import (
    build_record,
    canonical_fact_type,
    fact_envelope,
)
from engine.models.sql.clinical_fact import ClinicalFact
from engine.models.sql.clinical_source import (
    ClinicalSource,
    ClinicalSourceKind,
    ExtractionStatus,
)
from engine.models.sql.document import Document
from engine.models.sql.person import Person
from engine.utils.misc import require_id

if typing.TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterable
    from datetime import datetime

    from engine.models.clinical_facts import PersonClinicalRecord
    from engine.models.extracted_fact_create import ExtractedFactCreate
    from engine.services.person.person_service import PersonService


class TransformedDocument(BaseModel):
    """Generic persistence entities produced for one imported artifact."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    document: Document
    clinical_sources: list[ClinicalSource]
    clinical_facts: list[ClinicalFact]


class PersonTransformationResult(BaseModel):
    """Transformation output for one ingestion request."""

    documents: list[TransformedDocument]


class ClinicalFactTransformer:
    """Create document, source, and fact records from extractor output."""

    def __init__(self, person_service: PersonService | None = None) -> None:
        """Store the optional resident identity resolver."""
        self.person_service = person_service

    def transform(
        self,
        document_path: pathlib.Path,
        facts: Iterable[ExtractedFactCreate],
        *,
        extractor_name: str,
        source_observed_at: datetime | None = None,
        existing_sources: Iterable[ClinicalSource] = (),
    ) -> TransformedDocument:
        """Build one validated document/source/fact persistence graph."""
        document = self._build_document(
            document_path,
            extractor_name,
            source_observed_at=source_observed_at,
        )
        sources = list(existing_sources)
        persisted_facts: list[ClinicalFact] = []
        source_by_key = {source.source_key: source for source in sources}
        seen_facts: set[tuple[str, str, str]] = set()
        content_by_page: dict[int | None, tuple[str | None, str | None]] = {}

        for create in facts:
            person = self._resolve_person(create)
            person_id = require_id(person.id)
            record = build_record(create, person_id=person_id)
            fact_type = canonical_fact_type(create.payload)
            envelope = fact_envelope(record, fact_type)

            source: ClinicalSource | None = None
            source_id = create.clinical_source_id
            if source_id is None:
                source_key = self._source_key(document, create, person_id, fact_type)
                source = source_by_key.get(source_key)
                if source is None:
                    content, raw_content = content_by_page.setdefault(
                        create.source_page,
                        self._source_content(document_path, create.source_page),
                    )
                    source = ClinicalSource(
                        document=document,
                        person_id=person_id,
                        source_kind=self._source_kind(extractor_name, fact_type),
                        source_key=source_key,
                        content=content,
                        raw_content=raw_content,
                        content_hash=self.content_hash(raw_content or content),
                        effective_at=envelope["effective_at"],
                        page_start=create.source_page,
                        page_end=create.source_page,
                        source_section=fact_type,
                        locator={"page": create.source_page}
                        if create.source_page is not None
                        else {},
                        source_system=create.source_system,
                        source_record_type=create.source_record_type,
                        source_record_id=create.source_record_id,
                        source_record_version=create.source_record_version,
                        source_document_id=create.source_document_id,
                        source_endpoint=create.source_endpoint,
                        source_authority=create.source_authority,
                        extraction_status=ExtractionStatus.EXTRACTED,
                    )
                    source_by_key[source_key] = source
                    sources.append(source)
            else:
                source_key = f"stored:{source_id}"

            identity = (
                source_key,
                fact_type,
                typing.cast("str", envelope["identity_hash"]),
            )
            if identity in seen_facts:
                continue
            seen_facts.add(identity)
            fact_values: dict[str, typing.Any] = {
                "person_id": person_id,
                "clinical_source_id": source_id,
                "fact_type": fact_type,
                "extraction_method": create.extraction_method,
                "confidence": create.confidence,
                "confidence_reason": create.confidence_reason,
                "model_name": create.model_name,
                "extractor_name": extractor_name,
                **envelope,
            }
            if source is not None:
                fact_values["source"] = source
            clinical_fact = ClinicalFact(
                **fact_values,
            )
            persisted_facts.append(clinical_fact)

        if not sources and not persisted_facts:
            content, raw_content = self._source_content(document_path, None)
            sources.append(
                ClinicalSource(
                    document=document,
                    source_kind=ClinicalSourceKind.REPORT_SECTION,
                    source_key=self._hash((document.checksum, "document")),
                    content=content,
                    raw_content=raw_content,
                    content_hash=self.content_hash(raw_content or content),
                    source_section="document",
                    extraction_status=ExtractionStatus.NOT_APPLICABLE,
                ),
            )
        return TransformedDocument(
            document=document,
            clinical_sources=sources,
            clinical_facts=persisted_facts,
        )

    @staticmethod
    def build_record(
        create: ExtractedFactCreate,
        *,
        person_id: int,
    ) -> PersonClinicalRecord:
        """Expose domain normalization for non-persistent demo consumers."""
        return build_record(create, person_id=person_id)

    @staticmethod
    def _build_document(
        document_path: pathlib.Path,
        document_type: str,
        *,
        source_observed_at: datetime | None = None,
    ) -> Document:
        media_type = mimetypes.guess_type(document_path.name)[0]
        return Document(
            filename=document_path.name,
            media_type=media_type or "application/octet-stream",
            checksum=ClinicalFactTransformer.document_checksum(document_path),
            storage_uri=document_path.resolve().as_uri(),
            byte_size=document_path.stat().st_size,
            document_type=document_type,
            source_observed_at=source_observed_at,
        )

    @staticmethod
    def document_checksum(document_path: pathlib.Path) -> str:
        """Return the artifact's stable SHA-256 identity."""
        content_digest = hashlib.sha256(document_path.read_bytes()).hexdigest()
        return f"sha256:{content_digest}"

    @staticmethod
    def _source_key(
        document: Document,
        create: ExtractedFactCreate,
        person_id: int,
        fact_type: str,
    ) -> str:
        return ClinicalFactTransformer._hash(
            {
                "document": document.checksum,
                "person_id": person_id,
                "page": create.source_page,
                "fact_type": fact_type,
                "source_system": create.source_system,
                "record_type": create.source_record_type,
                "record_id": create.source_record_id,
                "record_version": create.source_record_version,
            },
        )

    @staticmethod
    def _source_kind(extractor_name: str, fact_type: str) -> ClinicalSourceKind:
        if extractor_name == "PccOrderReportExtractor":
            return ClinicalSourceKind.ORDER_ENTRY
        if extractor_name == "PccLabResultsExtractor" or fact_type == "lab":
            return ClinicalSourceKind.LAB_SECTION
        if extractor_name == "WoundReportExtractor" or fact_type == "wound":
            return ClinicalSourceKind.WOUND_ENTRY
        if extractor_name == "UnknownFileExtractor":
            return ClinicalSourceKind.TEXT_BLOCK
        return ClinicalSourceKind.REPORT_SECTION

    @staticmethod
    def _source_content(
        path: pathlib.Path,
        page: int | None,
    ) -> tuple[str | None, str | None]:
        """Retain the original logical source text when the format permits it."""
        suffix = path.suffix.casefold()
        if suffix in {".txt", ".csv"}:
            raw = path.read_text(encoding="utf-8", errors="replace")
            return "\n".join(line.rstrip() for line in raw.splitlines()).strip(), raw
        if suffix != ".pdf":
            return None, None
        try:
            with pymupdf.open(path) as document:
                if page is not None and 1 <= page <= document.page_count:
                    raw = document[page - 1].get_text()
                else:
                    raw = "\n".join(pdf_page.get_text() for pdf_page in document)
        except (pymupdf.FileDataError, pymupdf.EmptyFileError):
            # A source may already have been parsed by a format-specific
            # extractor or supplied by a test/import adapter. Its structured
            # facts remain valid even if the original bytes are unavailable to
            # MuPDF; provenance metadata still retains the file and locator.
            return None, None
        return "\n".join(line.rstrip() for line in raw.splitlines()).strip(), raw

    def _resolve_person(self, create: ExtractedFactCreate) -> Person:
        if create.person_id is not None:
            return Person(id=create.person_id, name=create.source_person_name or "")
        if self.person_service is None:
            msg = "A person service is required to transform resident facts"
            raise RuntimeError(msg)
        return self.person_service.resolve_or_create_person(
            source_person_identifier=create.source_person_identifier,
            source_person_name=create.source_person_name,
            date_of_birth=create.date_of_birth,
            sex=create.sex,
            height_in=create.height_in,
        )

    @staticmethod
    def content_hash(content: str | None) -> str | None:
        """Return a content digest when source material is available."""
        return None if content is None else hashlib.sha256(content.encode()).hexdigest()

    @staticmethod
    def _hash(value: object) -> str:
        serialized = json.dumps(
            value,
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(serialized.encode()).hexdigest()


__all__ = [
    "ClinicalFactTransformer",
    "PersonTransformationResult",
    "TransformedDocument",
]
