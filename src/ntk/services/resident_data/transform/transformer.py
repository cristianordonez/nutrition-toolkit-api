"""Transform transient extraction results into SQLModel entities."""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import typing
from datetime import UTC, date, datetime, time

from pydantic import BaseModel, ConfigDict, SerializeAsAny

from ntk.models.sql.clinical import (
    ResidentClinicalFact,
    ResidentEdema,
    ResidentLab,
    ResidentMealIntake,
    ResidentOrder,
    ResidentWeight,
    ResidentWound,
)
from ntk.models.sql.document import Document, DocumentSource, DocumentSourceType
from ntk.models.sql.extracted_fact import ExtractedFact
from ntk.services.resident_data.resident_resolver import (
    ResidentResolution,
    ResidentResolver,
)

if typing.TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterable

    from sqlmodel import SQLModel

    from ntk.models.extracted_fact_create import ExtractedFactCreate
logger = logging.getLogger(__name__)

ResidentFactModel: typing.TypeAlias = (
    ResidentClinicalFact
    | ResidentEdema
    | ResidentLab
    | ResidentMealIntake
    | ResidentOrder
    | ResidentWeight
    | ResidentWound
)


# Central routing from typed fact discriminator to canonical domain model.
DOMAIN_MODEL_BY_FACT_TYPE: dict[str, type[SQLModel]] = {
    "clinical_fact": ResidentClinicalFact,
    "edema": ResidentEdema,
    "intake": ResidentMealIntake,
    "lab": ResidentLab,
    "order": ResidentOrder,
    "weight": ResidentWeight,
    "wound": ResidentWound,
}

_EFFECTIVE_FIELD_BY_FACT_TYPE = {
    "clinical_fact": "observed_at",
    "edema": "observed_at",
    "intake": "observed_at",
    "lab": "observed_at",
    "order": "revision_date",
    "weight": "measured_at",
    "wound": "observed_at",
}

_SOURCE_TYPE_BY_SUFFIX = {
    ".csv": DocumentSourceType.CSV,
    ".pdf": DocumentSourceType.PDF,
    ".txt": DocumentSourceType.TEXT,
}


class TransformedDocument(BaseModel):
    """SQLModel entities produced for one imported document."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    document: Document
    document_sources: list[DocumentSource]
    extracted_facts: list[ExtractedFact]
    related_models: list[SerializeAsAny[ResidentFactModel]]


class ResidentTransformationResult(BaseModel):
    """Transformation output for a resident-ingestion request."""

    documents: list[TransformedDocument]


class ExtractedFactTransformer:
    """Convert transient facts and their source document into SQL models."""

    def __init__(
        self,
        resident_resolver: ResidentResolver | None = None,
    ) -> None:
        """Store the resolver for external resident identifiers."""
        self.resident_resolver = resident_resolver

    def transform(
        self,
        document_path: pathlib.Path,
        facts: Iterable[ExtractedFactCreate],
        *,
        extractor_name: str,
    ) -> TransformedDocument:
        """Create document, provenance, fact, and related resident models."""
        document = self._build_document(document_path, extractor_name)
        document_sources: list[DocumentSource] = []
        extracted_facts: list[ExtractedFact] = []
        related_models: list[ResidentFactModel] = []
        source_by_evidence: dict[tuple[int | None, str], DocumentSource] = {}
        seen_facts: set[tuple[str, str]] = set()
        for create in facts:
            fact_type = create.payload.type
            evidence_hash = self._evidence_hash(create)
            source_identity = (create.source_page, evidence_hash)
            source = source_by_evidence.get(source_identity)
            if source is None:
                source = DocumentSource(
                    document_id=typing.cast("int", document.id),
                    document=document,
                    source_type=self._source_type(document_path),
                    source_page=create.source_page,
                    evidence_hash=evidence_hash,
                    source_section=fact_type,
                )
                source_by_evidence[source_identity] = source
                document_sources.append(source)
            logger.debug("Transforming fact: %s from source %s", create, source)
            resolution = self._resolve_resident(create)
            payload = create.payload.model_dump(mode="json", exclude={"type"})
            extracted_fact = ExtractedFact(
                resident_id=resolution.resident_id,
                facility_id=resolution.facility_id,
                resident_facility_stay_id=resolution.resident_facility_stay_id,
                progress_note_id=create.progress_note_id,
                resident_name=create.resident_name,
                facility_resident_identifier=create.facility_resident_identifier,
                facility_name=create.facility_name,
                source_id=source.id,
                source_page=create.source_page,
                fact_type=fact_type,
                payload=payload,
                effective_at=self._effective_at(create),
                confidence=create.confidence,
                confidence_reason=create.confidence_reason,
                model_name=create.model_name,
                extractor_name=extractor_name,
                transformed_at=datetime.now(UTC),
            )
            identity = (
                f"{source.source_page}:{source.evidence_hash}",
                extracted_fact.fact_key,
            )
            if identity in seen_facts:
                continue
            seen_facts.add(identity)
            extracted_fact.source = source
            extracted_facts.append(extracted_fact)
            related_models.append(
                self._build_related_model(
                    create,
                    extracted_fact,
                    resolution.resident_id,
                    resolution.resident_facility_stay_id,
                ),
            )
        if not document_sources:
            document_sources.append(
                DocumentSource(
                    document_id=typing.cast("int", document.id),
                    document=document,
                    source_type=self._source_type(document_path),
                    evidence_hash=document.checksum.removeprefix("sha256:"),
                    source_section="document",
                ),
            )
        return TransformedDocument(
            document=document,
            document_sources=document_sources,
            extracted_facts=extracted_facts,
            related_models=related_models,
        )

    @staticmethod
    def _build_document(document_path: pathlib.Path, document_type: str) -> Document:
        file_type = mimetypes.guess_type(document_path.name)[0]
        return Document(
            filename=document_path.name,
            file_type=file_type or "application/octet-stream",
            checksum=ExtractedFactTransformer.document_checksum(document_path),
            storage_uri=document_path.resolve().as_uri(),
            document_type=document_type,
        )

    @staticmethod
    def document_checksum(document_path: pathlib.Path) -> str:
        """Return the canonical content checksum used for document identity."""
        content_digest = hashlib.sha256(document_path.read_bytes()).hexdigest()
        return f"sha256:{content_digest}"

    @staticmethod
    def _source_type(document_path: pathlib.Path) -> DocumentSourceType:
        try:
            return _SOURCE_TYPE_BY_SUFFIX[document_path.suffix.casefold()]
        except KeyError as error:
            suffix = document_path.suffix or "<none>"
            msg = f"Unsupported document source type: {suffix}"
            raise TypeError(msg) from error

    @staticmethod
    def _evidence_hash(create: ExtractedFactCreate) -> str:
        evidence = json.dumps(
            {
                "facility_resident_identifier": (create.facility_resident_identifier),
                "resident_name": create.resident_name,
                "facility_name": create.facility_name,
                "date_of_birth": (
                    create.date_of_birth.isoformat()
                    if create.date_of_birth is not None
                    else None
                ),
                "sex": create.sex,
                "height_in": create.height_in,
                "payload": create.payload.model_dump(mode="json"),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(evidence.encode("utf-8")).hexdigest()

    def _resolve_resident(self, create: ExtractedFactCreate) -> ResidentResolution:
        if create.resident_facility_stay_id is not None:
            if self.resident_resolver is None:
                msg = "A resident resolver is required to resolve a facility stay"
                raise RuntimeError(msg)
            resolution = self.resident_resolver.resolve_stay(
                create.resident_facility_stay_id,
            )
            if resolution is None:
                msg = (
                    "Resident facility stay "
                    f"{create.resident_facility_stay_id} was not found"
                )
                raise ValueError(msg)
            if (
                create.resident_id is not None
                and create.resident_id != resolution.resident_id
            ):
                msg = "Resident ID does not match the supplied facility stay"
                raise ValueError(msg)
            return resolution
        if create.resident_id is not None:
            facility_id = create.facility_id
            if (
                facility_id is None
                and create.facility_name is not None
                and self.resident_resolver is not None
            ):
                facility = self.resident_resolver.facility_repository.get_by_name(
                    create.facility_name,
                )
                facility_id = facility.id if facility is not None else None
            return ResidentResolution(
                resident_id=create.resident_id,
                resident_facility_stay_id=create.resident_facility_stay_id,
                facility_id=facility_id,
            )
        if self.resident_resolver is None:
            msg = "A resident resolver is required to transform resident facts"
            raise RuntimeError(msg)
        return self.resident_resolver.resolve_or_create_resident(
            facility_name=create.facility_name,
            facility_resident_identifier=create.facility_resident_identifier,
            resident_name=create.resident_name,
            date_of_birth=create.date_of_birth,
            sex=create.sex,
            height_in=create.height_in,
            effective_at=self._effective_at(create),
        )

    @staticmethod
    def _effective_at(create: ExtractedFactCreate) -> datetime | None:
        fact_type = create.payload.type
        field_name = _EFFECTIVE_FIELD_BY_FACT_TYPE.get(fact_type)
        if field_name is None:
            return None
        value = getattr(create.payload, field_name, None)
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time.min, tzinfo=UTC)
        return None

    @staticmethod
    def _build_related_model(
        create: ExtractedFactCreate,
        extracted_fact: ExtractedFact,
        resident_id: int,
        resident_facility_stay_id: int | None,
    ) -> ResidentFactModel:
        fact_type = create.payload.type
        try:
            model_type = DOMAIN_MODEL_BY_FACT_TYPE[fact_type]
        except KeyError as error:
            msg = f"Unsupported resident fact type: {fact_type}"
            raise ValueError(msg) from error
        payload = create.payload.model_dump(mode="python", exclude={"type"})
        if fact_type == "wound":
            payload["type"] = payload.pop("wound_type")
            payload["location"] = payload.get("location") or "Unspecified"
        elif fact_type == "edema":
            payload["location"] = payload.get("location") or "Unspecified"
        payload.update(
            resident_id=resident_id,
            resident_facility_stay_id=resident_facility_stay_id,
            extracted_fact_id=extracted_fact.id,
        )
        model = typing.cast(
            "ResidentFactModel",
            model_type.model_validate(payload),
        )
        model.extracted_fact = extracted_fact
        return model


__all__ = [
    "DOMAIN_MODEL_BY_FACT_TYPE",
    "ExtractedFactTransformer",
    "ResidentFactModel",
    "ResidentTransformationResult",
    "TransformedDocument",
]
