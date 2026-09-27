"""Central mapping between fact discriminators and typed Pydantic records."""

from __future__ import annotations

import hashlib
import json
import typing
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from engine.models.clinical_facts import (
    ClinicalRecord,
    PersonAllergy,
    PersonAppetiteObservation,
    PersonClinicalFact,
    PersonClinicalRecord,
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
    build_state_key,
    normalize_clinical_text,
)
from engine.models.extracted_fact_create import (
    AllergyPayload,
    AppetitePayload,
    ClinicalFactPayload,
    DiagnosisPayload,
    DialysisPayload,
    DietPayload,
    EdemaPayload,
    EnteralFeedingPayload,
    FluidPlanPayload,
    FoodPreferencePayload,
    GIObservationPayload,
    LabPayload,
    MealIntakePayload,
    MedicationPayload,
    MiscOrderPayload,
    NutritionGoalPayload,
    OralFeedingStatusPayload,
    ParenteralNutritionPayload,
    PersonFactPayload,
    SupplementPayload,
    WeightPayload,
    WoundPayload,
)

if typing.TYPE_CHECKING:
    from pydantic import BaseModel

    from engine.models.extracted_fact_create import ExtractedFactCreate
    from engine.models.sql.clinical_fact import ClinicalFact


@dataclass(frozen=True, slots=True)
class FactDefinition:
    """Validation and hydration behavior for one persisted fact type."""

    payload_model: type[BaseModel]
    record_model: type[ClinicalRecord]


FACT_DEFINITIONS: dict[str, FactDefinition] = {
    "weight": FactDefinition(WeightPayload, PersonWeight),
    "lab": FactDefinition(LabPayload, PersonLab),
    "edema": FactDefinition(EdemaPayload, PersonEdema),
    "wound": FactDefinition(WoundPayload, PersonWound),
    "meal_intake": FactDefinition(MealIntakePayload, PersonMealIntake),
    "appetite": FactDefinition(AppetitePayload, PersonAppetiteObservation),
    "gi_observation": FactDefinition(GIObservationPayload, PersonGIObservation),
    "medication": FactDefinition(MedicationPayload, PersonMedication),
    "diagnosis": FactDefinition(DiagnosisPayload, PersonDiagnosis),
    "allergy": FactDefinition(AllergyPayload, PersonAllergy),
    "diet": FactDefinition(DietPayload, PersonDiet),
    "enteral_feeding": FactDefinition(EnteralFeedingPayload, PersonEnteralFeeding),
    "parenteral_nutrition": FactDefinition(
        ParenteralNutritionPayload,
        PersonParenteralNutrition,
    ),
    "supplement": FactDefinition(SupplementPayload, PersonSupplement),
    "dialysis": FactDefinition(DialysisPayload, PersonDialysis),
    "fluid_plan": FactDefinition(FluidPlanPayload, PersonFluidPlan),
    "oral_feeding_status": FactDefinition(
        OralFeedingStatusPayload,
        PersonOralFeedingStatus,
    ),
    "food_preference": FactDefinition(FoodPreferencePayload, PersonFoodPreference),
    "misc_order": FactDefinition(MiscOrderPayload, PersonMiscOrder),
    "nutrition_goal": FactDefinition(NutritionGoalPayload, PersonNutritionGoal),
    "clinical_observation": FactDefinition(ClinicalFactPayload, PersonClinicalFact),
    "clinical_event": FactDefinition(ClinicalFactPayload, PersonClinicalFact),
}

_STATEFUL_TYPES = {
    "allergy",
    "diagnosis",
    "dialysis",
    "diet",
    "enteral_feeding",
    "fluid_plan",
    "food_preference",
    "medication",
    "misc_order",
    "nutrition_goal",
    "oral_feeding_status",
    "parenteral_nutrition",
    "supplement",
}
_OBSERVATION_TYPES = {"appetite", "gi_observation"}
_SOURCE_ONLY_FIELDS = {
    "action",
    "source_category",
    "source_revision_date",
    "type",
}
_RECORD_METADATA_FIELDS = {
    "id",
    "person_id",
    "clinical_source_id",
    "created_at",
    "state_key",
    "observation_key",
}


def canonical_fact_type(payload: PersonFactPayload) -> str:
    """Return the persisted discriminator for an extractor payload."""
    source_type = str(payload.type)
    if source_type == "intake":
        return "meal_intake"
    if isinstance(payload, ClinicalFactPayload):
        return f"clinical_{payload.clinical_fact_type}"
    return source_type


def build_record(
    create: ExtractedFactCreate,
    *,
    person_id: int,
) -> PersonClinicalRecord:
    """Normalize one validated extraction payload into a domain record."""
    fact_type = canonical_fact_type(create.payload)
    definition = FACT_DEFINITIONS[fact_type]
    payload = create.payload.model_dump(mode="python", exclude=_SOURCE_ONLY_FIELDS)
    revision_at = _revision_datetime(create.payload)
    if "effective_at" in definition.record_model.model_fields:
        payload["effective_at"] = payload.get("effective_at") or revision_at
    if fact_type == "wound":
        payload["type"] = payload.pop("wound_type")
        payload["location"] = payload.get("location") or "Unspecified"
    elif fact_type == "edema":
        payload["location"] = payload.get("location") or "Unspecified"
    if fact_type in _STATEFUL_TYPES:
        payload["state_key"] = _state_key(
            fact_type,
            create.payload.model_dump(mode="python", exclude={"type"}),
        )
    elif fact_type in _OBSERVATION_TYPES:
        payload["observation_key"] = build_state_key(
            fact_type,
            create.payload.model_dump(mode="python", exclude={"type"}),
        )
    payload["person_id"] = person_id
    return typing.cast(
        "PersonClinicalRecord",
        definition.record_model.model_validate(payload),
    )


def serialize_record(record: PersonClinicalRecord) -> dict[str, typing.Any]:
    """Serialize only clinical payload fields, excluding persistence metadata."""
    return record.model_dump(mode="json", exclude=_RECORD_METADATA_FIELDS)


def hydrate_fact(fact: ClinicalFact) -> PersonClinicalRecord:
    """Validate a stored payload and attach its envelope metadata."""
    try:
        definition = FACT_DEFINITIONS[fact.fact_type]
    except KeyError as error:
        msg = f"Unsupported persisted fact type: {fact.fact_type}"
        raise ValueError(msg) from error
    payload = dict(fact.payload)
    payload.update(
        id=fact.id,
        person_id=fact.person_id,
        clinical_source_id=fact.clinical_source_id,
        created_at=fact.created_at,
    )
    if "state_key" in definition.record_model.model_fields:
        payload["state_key"] = fact.concept_key
    if "observation_key" in definition.record_model.model_fields:
        payload["observation_key"] = fact.identity_hash
    return typing.cast(
        "PersonClinicalRecord",
        definition.record_model.model_validate(payload),
    )


def fact_envelope(
    record: PersonClinicalRecord,
    fact_type: str,
) -> dict[str, typing.Any]:
    """Derive indexed persistence columns and hashes from one domain record."""
    payload = serialize_record(record)
    content_hash = _hash({"fact_type": fact_type, "payload": payload})
    effective_at = getattr(record, "effective_at", None)
    observed_at = getattr(record, "observed_at", None)
    if isinstance(record, PersonWeight):
        effective_at = record.measured_at
        observed_at = record.measured_at
    elif effective_at is None:
        effective_at = observed_at
    ended_at = getattr(record, "discontinued_at", None)
    status = getattr(record, "status", None)
    lifecycle_status = None if status is None else str(getattr(status, "value", status))
    concept_key = _concept_key(record, fact_type)
    identity = _identity(record, fact_type, concept_key, effective_at, content_hash)
    return {
        "payload": payload,
        "effective_at": effective_at,
        "observed_at": observed_at,
        "ended_at": ended_at,
        "lifecycle_status": lifecycle_status,
        "concept_key": concept_key,
        "identity_hash": _hash(identity),
        "content_hash": content_hash,
    }


def _revision_datetime(payload: object) -> datetime | None:
    value = getattr(payload, "source_revision_date", None)
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    return None


def _state_key(fact_type: str, payload: dict[str, object]) -> str:
    excluded = {
        "action",
        "discontinued_at",
        "effective_at",
        "instructions",
        "observed_at",
        "source_category",
        "status",
    }

    def normalize(value: object) -> object:
        if isinstance(value, str):
            return normalize_clinical_text(value)
        if isinstance(value, list):
            return sorted((normalize(item) for item in value), key=repr)
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


def _concept_key(  # noqa: PLR0911 - explicit domain routing is clearer than dispatch
    record: PersonClinicalRecord,
    fact_type: str,
) -> str | None:
    if fact_type == "diet":
        return "current-diet"
    if record.state_key:
        return record.state_key
    if isinstance(record, PersonLab):
        return normalize_clinical_text(record.name)
    if isinstance(record, PersonEdema):
        return normalize_clinical_text(record.location)
    if isinstance(record, PersonWound):
        return normalize_clinical_text(
            record.wound_number or f"{record.type}:{record.location}",
        )
    if isinstance(record, PersonClinicalFact):
        return normalize_clinical_text(record.observation_type)
    return None


def _identity(  # noqa: PLR0911 - each fact family has a distinct natural key
    record: PersonClinicalRecord,
    fact_type: str,
    concept_key: str | None,
    effective_at: datetime | None,
    content_hash: str,
) -> object:
    if isinstance(record, PersonWeight):
        return (fact_type, _canonical_datetime(record.measured_at))
    if isinstance(record, PersonLab):
        return (fact_type, concept_key, _canonical_datetime(record.observed_at))
    if isinstance(record, PersonEdema):
        return (fact_type, concept_key, _canonical_datetime(record.observed_at))
    if isinstance(record, PersonWound):
        return (fact_type, concept_key, _canonical_datetime(record.observed_at))
    if record.state_key:
        return (fact_type, record.state_key)
    if record.observation_key:
        return (fact_type, record.observation_key)
    if effective_at is not None:
        return (
            fact_type,
            concept_key,
            _canonical_datetime(effective_at),
            content_hash,
        )
    return (fact_type, content_hash)


def _canonical_datetime(value: datetime) -> str:
    """Normalize equivalent naive/offset timestamps for fact identity."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _hash(value: object) -> str:
    serialized = json.dumps(
        value,
        default=str,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


__all__ = [
    "FACT_DEFINITIONS",
    "FactDefinition",
    "build_record",
    "canonical_fact_type",
    "fact_envelope",
    "hydrate_fact",
    "serialize_record",
]
