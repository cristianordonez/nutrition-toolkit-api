"""Facts extracted from imported document sources."""

from __future__ import annotations

import hashlib
import json
import logging
import typing
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import model_validator
from sqlalchemy import JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

from .document import Document, DocumentSource, DocumentSourceType

if typing.TYPE_CHECKING:
    from .clinical import (
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
    from .person import Person

logger = logging.getLogger(__name__)


class ExtractionMethod(StrEnum):
    """Method used to produce a source fact."""

    DETERMINISTIC = "deterministic"
    AI = "ai"
    API = "api"
    IMPORT = "import"
    MANUAL = "manual"


def build_fact_key(
    fact_type: str,
    payload: dict[str, typing.Any],
    effective_at: datetime | None,
    observed_at: datetime | None = None,
) -> str:
    """Return a stable SHA-256 identity for the normalized fact content."""
    serialized_fact = json.dumps(
        {
            "fact_type": fact_type,
            "payload": payload,
            "observed_at": observed_at,
            "effective_at": effective_at,
        },
        default=str,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized_fact.encode("utf-8")).hexdigest()


class ExtractedFact(SQLModel, table=True):
    """A normalized fact extracted from one document source."""

    __tablename__ = "extracted_fact"
    __table_args__ = (UniqueConstraint("source_id", "fact_key"),)

    id: int | None = Field(default=None, primary_key=True)

    # Resolved identity
    person_id: int | None = Field(
        default=None,
        foreign_key="person.id",
        index=True,
    )
    facility_id: int | None = Field(
        default=None,
        foreign_key="facility.id",
        index=True,
    )
    progress_note_id: int | None = Field(
        default=None,
        foreign_key="person_progress_note.id",
        index=True,
    )

    # Extracted identity hints
    source_person_name: str | None = None
    source_person_identifier: str | None = Field(default=None, index=True)
    facility_name: str | None = None
    source_facility_identifier: str | None = Field(default=None, index=True)

    # Source
    source_id: int | None = Field(
        default=None,
        foreign_key="document_source.id",
        index=True,
    )
    source_page: int | None = Field(
        default=None,
        index=True,
    )

    # Fact
    fact_key: str = Field(default="", max_length=64, index=True)
    fact_type: str = Field(index=True)
    payload: dict[str, typing.Any] = Field(sa_type=JSON)
    observed_at: datetime | None = Field(default=None, index=True)
    effective_at: datetime | None = Field(default=None, index=True)

    # Extraction metadata
    extraction_method: ExtractionMethod = Field(
        default=ExtractionMethod.DETERMINISTIC,
        index=True,
    )
    confidence: float
    confidence_reason: str | None = None
    model_name: str | None = None
    extractor_name: str | None = None
    extractor_version: str | None = None
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    transformed_at: datetime | None = None

    # Relationships
    source: DocumentSource = Relationship(back_populates="extracted_facts")
    person: Person = Relationship(back_populates="extracted_facts")
    diagnoses: list[PersonDiagnosis] = Relationship(
        sa_relationship=relationship(
            "PersonDiagnosis",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    allergies: list[PersonAllergy] = Relationship(
        sa_relationship=relationship(
            "PersonAllergy",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    appetite_observations: list[PersonAppetiteObservation] = Relationship(
        sa_relationship=relationship(
            "PersonAppetiteObservation",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    medications: list[PersonMedication] = Relationship(
        sa_relationship=relationship(
            "PersonMedication",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    diets: list[PersonDiet] = Relationship(
        sa_relationship=relationship(
            "PersonDiet",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    enteral_feedings: list[PersonEnteralFeeding] = Relationship(
        sa_relationship=relationship(
            "PersonEnteralFeeding",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    parenteral_nutrition_records: list[PersonParenteralNutrition] = Relationship(
        sa_relationship=relationship(
            "PersonParenteralNutrition",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    fluid_plans: list[PersonFluidPlan] = Relationship(
        sa_relationship=relationship(
            "PersonFluidPlan",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    gi_observations: list[PersonGIObservation] = Relationship(
        sa_relationship=relationship(
            "PersonGIObservation",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    supplements: list[PersonSupplement] = Relationship(
        sa_relationship=relationship(
            "PersonSupplement",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    dialysis_records: list[PersonDialysis] = Relationship(
        sa_relationship=relationship(
            "PersonDialysis",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    oral_feeding_status_history: list[PersonOralFeedingStatus] = Relationship(
        sa_relationship=relationship(
            "PersonOralFeedingStatus",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    food_preferences: list[PersonFoodPreference] = Relationship(
        sa_relationship=relationship(
            "PersonFoodPreference",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    misc_orders: list[PersonMiscOrder] = Relationship(
        sa_relationship=relationship(
            "PersonMiscOrder",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    nutrition_goals: list[PersonNutritionGoal] = Relationship(
        sa_relationship=relationship(
            "PersonNutritionGoal",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    wounds: list[PersonWound] = Relationship(
        sa_relationship=relationship(
            "PersonWound",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    labs: list[PersonLab] = Relationship(
        sa_relationship=relationship(
            "PersonLab",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    edema: list[PersonEdema] = Relationship(
        sa_relationship=relationship(
            "PersonEdema",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    meal_intakes: list[PersonMealIntake] = Relationship(
        sa_relationship=relationship(
            "PersonMealIntake",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    clinical_facts: list[PersonClinicalFact] = Relationship(
        sa_relationship=relationship(
            "PersonClinicalFact",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    weights: list[PersonWeight] = Relationship(
        sa_relationship=relationship(
            "PersonWeight",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )

    def __init__(self, **data: typing.Any) -> None:  # noqa: ANN401
        """Generate the identity when constructed through SQLModel."""
        if {"fact_type", "payload"} <= data.keys():
            data["fact_key"] = build_fact_key(
                data["fact_type"],
                data["payload"],
                data.get("effective_at"),
                data.get("observed_at"),
            )
        super().__init__(**data)

    @model_validator(mode="before")
    @classmethod
    def generate_fact_key(cls, data: typing.Any) -> typing.Any:  # noqa: ANN401
        """Generate the content identity from the normalized fact fields."""
        if not isinstance(data, dict) or not {"fact_type", "payload"} <= data.keys():
            return data
        normalized_data = dict(data)
        normalized_data["fact_key"] = build_fact_key(
            normalized_data["fact_type"],
            normalized_data["payload"],
            normalized_data.get("effective_at"),
            normalized_data.get("observed_at"),
        )
        logger.debug("Fact key: %s", normalized_data["fact_key"])
        return normalized_data


__all__ = [
    "Document",
    "DocumentSource",
    "DocumentSourceType",
    "ExtractedFact",
    "ExtractionMethod",
    "build_fact_key",
]
