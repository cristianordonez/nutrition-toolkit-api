"""Person identity and clinical-note models."""

from __future__ import annotations

import typing
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import Column, Enum, UniqueConstraint, text
from sqlalchemy.orm import relationship
from sqlmodel import Field, Index, Relationship, SQLModel

from engine.models.sql.clinical import (
    ClinicalFactType,
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

if typing.TYPE_CHECKING:
    from engine.models.sql import Facility

    from .extracted_fact import ExtractedFact


class ExtractionStatus(StrEnum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    SKIPPED = "skipped"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


def normalize_person_name_part(value: str) -> str:
    """Return a stable comparison value for one person name component."""
    return " ".join(value.split()).casefold()


def parse_person_name(name: str) -> tuple[str, str]:
    """Split common clinical display-name formats into first and last names."""
    normalized = " ".join(name.split())
    if not normalized:
        return "", ""
    if "," in normalized:
        last_name, given_names = normalized.split(",", 1)
        first_name = (
            given_names.strip().split(maxsplit=1)[0] if given_names.strip() else ""
        )
        return first_name, last_name.strip()
    parts = normalized.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


class Person(SQLModel, table=True):
    __tablename__ = "person"
    __table_args__ = (
        UniqueConstraint(
            "normalized_first_name",
            "normalized_last_name",
            "date_of_birth",
            name="uq_person_natural_identity",
        ),
        Index(
            "uq_person_identifier_without_facility",
            "person_identifier",
            unique=True,
            postgresql_where=text(
                "facility_id IS NULL AND person_identifier IS NOT NULL",
            ),
            sqlite_where=text(
                "facility_id IS NULL AND person_identifier IS NOT NULL",
            ),
        ),
        Index(
            "uq_person_identifier_with_facility",
            "facility_id",
            "person_identifier",
            unique=True,
            postgresql_where=text(
                "facility_id IS NOT NULL AND person_identifier IS NOT NULL",
            ),
            sqlite_where=text(
                "facility_id IS NOT NULL AND person_identifier IS NOT NULL",
            ),
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    name: str
    first_name: str = Field(default="")
    last_name: str = Field(default="")
    normalized_first_name: str = Field(default="", index=True)
    normalized_last_name: str = Field(default="", index=True)
    date_of_birth: date | None = None
    facility_id: int | None = Field(default=None, foreign_key="facility.id", index=True)
    person_identifier: str | None = Field(default=None, index=True)
    sex: str | None = None
    height_in: float | None = Field(default=None, gt=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    facility: Facility | None = Relationship(
        sa_relationship=relationship("Facility", back_populates="persons"),
    )
    weights: list[PersonWeight] = Relationship(
        sa_relationship=relationship("PersonWeight", back_populates="person"),
    )
    diagnoses: list[PersonDiagnosis] = Relationship(
        sa_relationship=relationship("PersonDiagnosis", back_populates="person"),
    )
    allergies: list[PersonAllergy] = Relationship(
        sa_relationship=relationship("PersonAllergy", back_populates="person"),
    )
    medications: list[PersonMedication] = Relationship(
        sa_relationship=relationship("PersonMedication", back_populates="person"),
    )
    diets: list[PersonDiet] = Relationship(
        sa_relationship=relationship("PersonDiet", back_populates="person"),
    )
    enteral_feedings: list[PersonEnteralFeeding] = Relationship(
        sa_relationship=relationship(
            "PersonEnteralFeeding",
            back_populates="person",
        ),
    )
    supplements: list[PersonSupplement] = Relationship(
        sa_relationship=relationship("PersonSupplement", back_populates="person"),
    )
    dialysis_records: list[PersonDialysis] = Relationship(
        sa_relationship=relationship("PersonDialysis", back_populates="person"),
    )
    oral_feeding_status_history: list[PersonOralFeedingStatus] = Relationship(
        sa_relationship=relationship(
            "PersonOralFeedingStatus",
            back_populates="person",
        ),
    )
    parenteral_nutrition_records: list[PersonParenteralNutrition] = Relationship(
        sa_relationship=relationship(
            "PersonParenteralNutrition",
            back_populates="person",
        ),
    )
    fluid_plans: list[PersonFluidPlan] = Relationship(
        sa_relationship=relationship("PersonFluidPlan", back_populates="person"),
    )
    food_preferences: list[PersonFoodPreference] = Relationship(
        sa_relationship=relationship(
            "PersonFoodPreference",
            back_populates="person",
        ),
    )
    misc_orders: list[PersonMiscOrder] = Relationship(
        sa_relationship=relationship("PersonMiscOrder", back_populates="person"),
    )
    nutrition_goals: list[PersonNutritionGoal] = Relationship(
        sa_relationship=relationship("PersonNutritionGoal", back_populates="person"),
    )
    labs: list[PersonLab] = Relationship(
        sa_relationship=relationship("PersonLab", back_populates="person"),
    )
    edema: list[PersonEdema] = Relationship(
        sa_relationship=relationship(
            "PersonEdema",
            back_populates="person",
            collection_class=list,
        ),
    )
    meal_intakes: list[PersonMealIntake] = Relationship(
        sa_relationship=relationship(
            "PersonMealIntake",
            back_populates="person",
            collection_class=list,
        ),
    )
    appetite_observations: list[PersonAppetiteObservation] = Relationship(
        sa_relationship=relationship(
            "PersonAppetiteObservation",
            back_populates="person",
        ),
    )
    gi_observations: list[PersonGIObservation] = Relationship(
        sa_relationship=relationship("PersonGIObservation", back_populates="person"),
    )
    wounds: list[PersonWound] = Relationship(
        sa_relationship=relationship("PersonWound", back_populates="person"),
    )
    clinical_facts: list[PersonClinicalFact] = Relationship(
        sa_relationship=relationship(
            "PersonClinicalFact",
            back_populates="person",
            collection_class=list,
        ),
    )

    clinical_notes: list[PersonClinicalNote] = Relationship(
        sa_relationship=relationship(
            "PersonClinicalNote",
            back_populates="person",
            collection_class=list,
        ),
    )
    extracted_facts: list[ExtractedFact] = Relationship(
        sa_relationship=relationship(
            "ExtractedFact",
            back_populates="person",
            collection_class=list,
        ),
    )

    def __init__(self, **data: typing.Any) -> None:  # noqa: ANN401
        """Normalize person identity fields for direct model construction."""
        name = " ".join(str(data.get("name") or "").split())
        first_name = " ".join(str(data.get("first_name") or "").split())
        last_name = " ".join(str(data.get("last_name") or "").split())
        if not first_name and not last_name:
            first_name, last_name = parse_person_name(name)
        if not name:
            name = " ".join(part for part in (first_name, last_name) if part)
        data.update(
            name=name,
            first_name=first_name,
            last_name=last_name,
            normalized_first_name=normalize_person_name_part(first_name),
            normalized_last_name=normalize_person_name_part(last_name),
            person_identifier=(
                " ".join(str(data.get("person_identifier") or "").split()) or None
            ),
        )
        super().__init__(**data)


class PersonClinicalNote(SQLModel, table=True):
    """A locally persisted clinical note ingested from a document."""

    __tablename__ = "person_clinical_note"
    __table_args__ = (
        UniqueConstraint(
            "person_id",
            "note_key",
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    note_date: datetime = Field(index=True)
    note_type: str | None = None
    author: str | None = None
    note_text: str
    raw_text: str
    note_key: str = Field(index=True, unique=True)
    extraction_status: ExtractionStatus = Field(
        default=ExtractionStatus.PENDING,
        sa_column=Column(
            Enum(
                ExtractionStatus,
                name="extraction_status",
                values_callable=lambda enum_type: [item.value for item in enum_type],
            ),
            nullable=False,
            default="pending",
            index=True,
        ),
    )
    person: Person = Relationship(back_populates="clinical_notes")
    source_id: int | None = Field(
        default=None,
        foreign_key="document_source.id",
        index=True,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        index=True,
    )


__all__ = [
    "ClinicalFactType",
    "ExtractionStatus",
    "Person",
    "PersonAllergy",
    "PersonAppetiteObservation",
    "PersonClinicalFact",
    "PersonClinicalNote",
    "PersonDiagnosis",
    "PersonDialysis",
    "PersonDiet",
    "PersonEdema",
    "PersonEnteralFeeding",
    "PersonFluidPlan",
    "PersonFoodPreference",
    "PersonGIObservation",
    "PersonLab",
    "PersonMealIntake",
    "PersonMedication",
    "PersonMiscOrder",
    "PersonNutritionGoal",
    "PersonOralFeedingStatus",
    "PersonParenteralNutrition",
    "PersonSupplement",
    "PersonWeight",
    "PersonWound",
    "normalize_person_name_part",
    "parse_person_name",
]
