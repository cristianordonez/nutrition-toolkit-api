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
        ResidentClinicalFact,
        ResidentEdema,
        ResidentLab,
        ResidentMealIntake,
        ResidentOrder,
        ResidentWeight,
        ResidentWound,
    )
    from .resident import Resident

logger = logging.getLogger(__name__)


class ExtractionMethod(StrEnum):
    DETERMINISTIC = "deterministic"
    AI = "ai"


def build_fact_key(
    fact_type: str,
    payload: dict[str, typing.Any],
    effective_at: datetime | None,
) -> str:
    """Return a stable SHA-256 identity for the normalized fact content."""
    serialized_fact = json.dumps(
        {
            "fact_type": fact_type,
            "payload": payload,
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
    resident_id: int | None = Field(
        default=None,
        foreign_key="resident.id",
        index=True,
    )
    facility_id: int | None = Field(
        default=None,
        foreign_key="facility.id",
        index=True,
    )
    resident_facility_stay_id: int | None = Field(
        default=None,
        foreign_key="resident_facility_stay.id",
        index=True,
    )
    progress_note_id: int | None = Field(
        default=None,
        foreign_key="resident_progress_note.id",
        index=True,
    )

    # Extracted identity hints
    resident_name: str | None = None
    facility_resident_identifier: str | None = Field(default=None, index=True)
    facility_name: str | None = None

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
    effective_at: datetime | None = Field(default=None, index=True)

    # Extraction metadata
    confidence: float
    confidence_reason: str | None = None
    model_name: str | None = None
    extractor_name: str | None = None
    extractor_version: str | None = None
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    transformed_at: datetime | None = None

    @property
    def extraction_method(self) -> ExtractionMethod:
        """Report whether provenance identifies AI or deterministic extraction."""
        if self.model_name:
            return ExtractionMethod.AI
        return ExtractionMethod.DETERMINISTIC

    # Relationships
    source: DocumentSource = Relationship(back_populates="extracted_facts")
    resident: Resident = Relationship(back_populates="extracted_facts")
    wounds: list[ResidentWound] = Relationship(
        sa_relationship=relationship(
            "ResidentWound",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    labs: list[ResidentLab] = Relationship(
        sa_relationship=relationship(
            "ResidentLab",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    edema: list[ResidentEdema] = Relationship(
        sa_relationship=relationship(
            "ResidentEdema",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    meal_intakes: list[ResidentMealIntake] = Relationship(
        sa_relationship=relationship(
            "ResidentMealIntake",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    orders: list[ResidentOrder] = Relationship(
        sa_relationship=relationship(
            "ResidentOrder",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    clinical_facts: list[ResidentClinicalFact] = Relationship(
        sa_relationship=relationship(
            "ResidentClinicalFact",
            back_populates="extracted_fact",
            collection_class=list,
        ),
    )
    weights: list[ResidentWeight] = Relationship(
        sa_relationship=relationship(
            "ResidentWeight",
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
