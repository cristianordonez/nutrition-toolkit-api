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
    PersonAllergy,
    PersonAppetiteObservation,
    PersonClinicalFact,
    PersonDiagnosis,
    PersonDialysis,
    PersonDiet,
    PersonEdema,
    PersonEnteralFeeding,
    PersonFluidPlan,
    PersonFoodPreference,
    PersonGIObservation,
    PersonLab,
    PersonMealIntake,
    PersonMedication,
    PersonMiscOrder,
    PersonNutritionGoal,
    PersonOralFeedingStatus,
    PersonParenteralNutrition,
    PersonSupplement,
    PersonWeight,
    PersonWound,
)
from ntk.models.sql.clinical.common import build_state_key, normalize_clinical_text
from ntk.models.sql.document import Document, DocumentSource, DocumentSourceType
from ntk.models.sql.extracted_fact import ExtractedFact
from ntk.models.sql.person import Person
from ntk.utils.misc import require_id

if typing.TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterable

    from sqlmodel import SQLModel

    from ntk.models.extracted_fact_create import ExtractedFactCreate
    from ntk.services.facility_resolver import FacilityResolver
    from ntk.services.person.person_service import PersonService
logger = logging.getLogger(__name__)

PersonFactModel: typing.TypeAlias = (
    PersonClinicalFact
    | PersonAllergy
    | PersonAppetiteObservation
    | PersonDiagnosis
    | PersonDialysis
    | PersonDiet
    | PersonEdema
    | PersonEnteralFeeding
    | PersonFoodPreference
    | PersonFluidPlan
    | PersonGIObservation
    | PersonLab
    | PersonMealIntake
    | PersonMedication
    | PersonMiscOrder
    | PersonOralFeedingStatus
    | PersonParenteralNutrition
    | PersonSupplement
    | PersonWeight
    | PersonNutritionGoal
    | PersonWound
)


# Central routing from typed fact discriminator to canonical domain model.
DOMAIN_MODEL_BY_FACT_TYPE: dict[str, type[SQLModel]] = {
    "clinical_fact": PersonClinicalFact,
    "allergy": PersonAllergy,
    "appetite": PersonAppetiteObservation,
    "diagnosis": PersonDiagnosis,
    "dialysis": PersonDialysis,
    "diet": PersonDiet,
    "edema": PersonEdema,
    "enteral_feeding": PersonEnteralFeeding,
    "food_preference": PersonFoodPreference,
    "fluid_plan": PersonFluidPlan,
    "gi_observation": PersonGIObservation,
    "intake": PersonMealIntake,
    "lab": PersonLab,
    "medication": PersonMedication,
    "misc_order": PersonMiscOrder,
    "oral_feeding_status": PersonOralFeedingStatus,
    "parenteral_nutrition": PersonParenteralNutrition,
    "supplement": PersonSupplement,
    "weight": PersonWeight,
    "nutrition_goal": PersonNutritionGoal,
    "wound": PersonWound,
}

_OBSERVED_FIELD_BY_FACT_TYPE = {
    "clinical_fact": "observed_at",
    "allergy": "observed_at",
    "appetite": "observed_at",
    "diagnosis": "observed_at",
    "dialysis": "observed_at",
    "diet": "observed_at",
    "edema": "observed_at",
    "enteral_feeding": "observed_at",
    "food_preference": "observed_at",
    "fluid_plan": "observed_at",
    "gi_observation": "observed_at",
    "intake": "observed_at",
    "lab": "observed_at",
    "medication": "observed_at",
    "misc_order": "observed_at",
    "oral_feeding_status": "observed_at",
    "parenteral_nutrition": "observed_at",
    "supplement": "observed_at",
    "weight": "measured_at",
    "nutrition_goal": "observed_at",
    "wound": "observed_at",
}

_STATEFUL_FACT_TYPES = {
    "allergy",
    "diagnosis",
    "dialysis",
    "diet",
    "enteral_feeding",
    "fluid_plan",
    "food_preference",
    "medication",
    "misc_order",
    "oral_feeding_status",
    "parenteral_nutrition",
    "supplement",
    "nutrition_goal",
}

_OBSERVATION_FACT_TYPES = {"appetite", "gi_observation"}

_SOURCE_ONLY_PAYLOAD_FIELDS = {
    "action",
    "source_category",
    "source_revision_date",
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
    related_models: list[SerializeAsAny[PersonFactModel]]


class PersonTransformationResult(BaseModel):
    """Transformation output for a person-ingestion request."""

    documents: list[TransformedDocument]


class ExtractedFactTransformer:
    """Convert transient facts and their source document into SQL models."""

    def __init__(
        self,
        person_service: PersonService | None = None,
        facility_resolver: FacilityResolver | None = None,
    ) -> None:
        """Store the resolvers for extracted facility and person identities."""
        self.person_service = person_service
        self.facility_resolver = facility_resolver or (
            getattr(person_service, "facility_resolver", None)
            if person_service is not None
            else None
        )

    def transform(
        self,
        document_path: pathlib.Path,
        facts: Iterable[ExtractedFactCreate],
        *,
        extractor_name: str,
        source_observed_at: datetime | None = None,
    ) -> TransformedDocument:
        """Create document, provenance, fact, and related person models."""
        document = self._build_document(
            document_path,
            extractor_name,
            source_observed_at=source_observed_at,
        )
        document_sources: list[DocumentSource] = []
        extracted_facts: list[ExtractedFact] = []
        related_models: list[PersonFactModel] = []
        source_by_evidence: dict[tuple[int | None, str], DocumentSource] = {}
        seen_facts: set[tuple[str, str]] = set()
        resolved_facility_ids: set[int] = set()
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
                    source_system=create.source_system,
                    source_record_type=create.source_record_type,
                    source_record_id=create.source_record_id,
                    source_record_version=create.source_record_version,
                    source_document_id=create.source_document_id,
                    source_endpoint=create.source_endpoint,
                    source_authority=create.source_authority,
                )
                source_by_evidence[source_identity] = source
                document_sources.append(source)
            logger.debug("Transforming fact: %s from source %s", create, source)
            facility_id = self._resolve_facility_id(create)
            if facility_id is not None:
                resolved_facility_ids.add(facility_id)
            person = self._resolve_person(create, facility_id=facility_id)
            payload = create.payload.model_dump(mode="json", exclude={"type"})
            extracted_fact = ExtractedFact(
                person_id=require_id(person.id),
                facility_id=facility_id,
                progress_note_id=create.progress_note_id,
                source_person_name=create.source_person_name,
                source_person_identifier=create.source_person_identifier,
                facility_name=create.facility_name,
                source_facility_identifier=create.facility_identifier,
                source_id=source.id,
                source_page=create.source_page,
                fact_type=fact_type,
                payload=payload,
                observed_at=self._observed_at(create),
                effective_at=self._effective_at(create),
                extraction_method=create.extraction_method,
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
                self.build_related_model(
                    create,
                    person_id=require_id(person.id),
                    extracted_fact=extracted_fact,
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
        if len(resolved_facility_ids) == 1:
            document.facility_id = next(iter(resolved_facility_ids))
        return TransformedDocument(
            document=document,
            document_sources=document_sources,
            extracted_facts=extracted_facts,
            related_models=related_models,
        )

    @staticmethod
    def _build_document(
        document_path: pathlib.Path,
        document_type: str,
        *,
        source_observed_at: datetime | None = None,
    ) -> Document:
        file_type = mimetypes.guess_type(document_path.name)[0]
        return Document(
            filename=document_path.name,
            file_type=file_type or "application/octet-stream",
            checksum=ExtractedFactTransformer.document_checksum(document_path),
            storage_uri=document_path.resolve().as_uri(),
            document_type=document_type,
            source_observed_at=source_observed_at,
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
                "source_person_identifier": create.source_person_identifier,
                "source_person_name": create.source_person_name,
                "facility_name": create.facility_name,
                "facility_identifier": create.facility_identifier,
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

    def _resolve_facility_id(self, create: ExtractedFactCreate) -> int | None:
        if create.facility_id is not None:
            return create.facility_id
        if self.facility_resolver is None:
            return None
        facility = self.facility_resolver.resolve(
            create.facility_name,
            facility_identifier=create.facility_identifier,
        )
        return require_id(facility.id) if facility is not None else None

    def _resolve_person(
        self,
        create: ExtractedFactCreate,
        *,
        facility_id: int | None,
    ) -> Person:
        if create.person_id is not None:
            return Person(
                id=create.person_id,
                name=create.source_person_name or "",
                facility_id=facility_id,
            )
        if self.person_service is None:
            msg = "A person service is required to transform person facts"
            raise RuntimeError(msg)
        return self.person_service.resolve_or_create_person(
            facility_id=facility_id,
            source_person_identifier=create.source_person_identifier,
            source_person_name=create.source_person_name,
            date_of_birth=create.date_of_birth,
            sex=create.sex,
            height_in=create.height_in,
        )

    @staticmethod
    def _observed_at(create: ExtractedFactCreate) -> datetime | None:
        fact_type = create.payload.type
        field_name = _OBSERVED_FIELD_BY_FACT_TYPE.get(fact_type)
        if field_name is None:
            return None
        value = getattr(create.payload, field_name, None)
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time.min, tzinfo=UTC)
        return None

    @staticmethod
    def _effective_at(create: ExtractedFactCreate) -> datetime | None:
        value = getattr(create.payload, "effective_at", None)
        return value if isinstance(value, datetime) else None

    @staticmethod
    def build_related_model(
        create: ExtractedFactCreate,
        *,
        person_id: int,
        extracted_fact: ExtractedFact | None = None,
    ) -> PersonFactModel:
        """Normalize one transient payload into its domain model.

        A persisted ingestion supplies ``extracted_fact`` for provenance. Transient
        consumers such as the demo can omit it and retain the normalized model only
        in memory.
        """
        fact_type = create.payload.type
        try:
            model_type = DOMAIN_MODEL_BY_FACT_TYPE[fact_type]
        except KeyError as error:
            msg = f"Unsupported person fact type: {fact_type}"
            raise ValueError(msg) from error
        payload = create.payload.model_dump(mode="python", exclude={"type"})
        for field_name in _SOURCE_ONLY_PAYLOAD_FIELDS:
            payload.pop(field_name, None)
        if fact_type == "wound":
            payload["type"] = payload.pop("wound_type")
            payload["location"] = payload.get("location") or "Unspecified"
        elif fact_type == "edema":
            payload["location"] = payload.get("location") or "Unspecified"
        if fact_type in _STATEFUL_FACT_TYPES:
            payload["state_key"] = ExtractedFactTransformer._state_key(
                fact_type,
                create.payload.model_dump(mode="python", exclude={"type"}),
            )
        elif fact_type in _OBSERVATION_FACT_TYPES:
            payload["observation_key"] = ExtractedFactTransformer._observation_key(
                fact_type,
                create.payload.model_dump(mode="python", exclude={"type"}),
            )
        payload.update(
            person_id=person_id,
            extracted_fact_id=(
                extracted_fact.id if extracted_fact is not None else None
            ),
        )
        model = typing.cast(
            "PersonFactModel",
            model_type.model_validate(payload),
        )
        if extracted_fact is not None:
            model.extracted_fact = extracted_fact
        return model

    @staticmethod
    def _state_key(fact_type: str, payload: dict[str, object]) -> str:
        excluded = {
            "action",
            "discontinued_at",
            "effective_at",
            "instructions",
            "observed_at",
            "source_category",
            "source_revision_date",
            "status",
        }

        def normalize(value: object) -> object:
            if isinstance(value, str):
                return normalize_clinical_text(value)
            if isinstance(value, list):
                return sorted(
                    (normalize(item) for item in value),
                    key=repr,
                )
            if isinstance(value, dict):
                return {
                    key: normalize(item)
                    for key, item in sorted(value.items())
                    if key not in excluded
                }
            return value

        identity = {
            key: normalize(value)
            for key, value in sorted(payload.items())
            if key not in excluded
        }
        return build_state_key(fact_type, identity)

    @staticmethod
    def _observation_key(fact_type: str, payload: dict[str, object]) -> str:
        """Include source clinical time so equal observations retain history."""
        return build_state_key(fact_type, payload)


__all__ = [
    "DOMAIN_MODEL_BY_FACT_TYPE",
    "ExtractedFactTransformer",
    "PersonFactModel",
    "PersonTransformationResult",
    "TransformedDocument",
]
