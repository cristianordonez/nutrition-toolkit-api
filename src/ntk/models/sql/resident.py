"""SQL models for residents and their nutrition assessment snapshots."""

from __future__ import annotations

import typing
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, TypeAdapter
from pydantic import Field as PydanticField
from sqlalchemy import JSON, Column
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel

if typing.TYPE_CHECKING:
    from sqlalchemy.engine.interfaces import Dialect


class WeightHistoryEntry(BaseModel):
    """One dated or described historical weight."""

    date: str | None = None
    weight_lb: float | None = None
    description: str | None = None


class LabResult(BaseModel):
    """One laboratory result represented by the source."""

    name: str
    value: str | None = None
    unit: str | None = None
    date: str | None = None
    reference_range: str | None = None


class MedicationData(BaseModel):
    """One medication listed in the resident documents."""

    name: str
    dose: str | None = None
    route: str | None = None
    frequency: str | None = None
    indication: str | None = None


class WoundData(BaseModel):
    """Skin integrity and wound information."""

    type: str
    location: str
    weeks_in_treatment: int | None = None
    stage: str | None = None
    progress: str | None = None


class EdemaData(BaseModel):
    """Presence, location, and severity of edema."""

    present: bool | None = None
    locations: list[str] = PydanticField(default_factory=list)
    severity: str | None = None


class TubeFeedingData(BaseModel):
    """Current enteral feeding order, when present."""

    formula: str | None = None
    rate: str | None = None
    schedule: str | None = None
    flushes: str | None = None


class SupplementData(BaseModel):
    """One oral or nutrition supplement."""

    name: str
    amount: str | None = None
    frequency: str | None = None


class _PydanticJSON(TypeDecorator[object]):
    """Serialize validated Pydantic values into a database JSON column."""

    impl = JSON
    cache_ok = True

    def __init__(self, annotation: typing.Any) -> None:  # noqa: ANN401
        super().__init__()
        self._adapter = TypeAdapter(annotation)

    def process_bind_param(
        self,
        value: object | None,
        dialect: Dialect,
    ) -> object | None:
        """Convert Pydantic values to JSON-compatible Python values."""
        del dialect
        if value is None:
            return None
        return self._adapter.dump_python(value, mode="json")

    def process_result_value(
        self,
        value: object | None,
        dialect: Dialect,
    ) -> object | None:
        """Restore typed values when a snapshot is loaded."""
        del dialect
        if value is None:
            return None
        return self._adapter.validate_python(value)


class Resident(SQLModel, table=True):
    """A resident belonging to one facility."""

    __tablename__ = "resident"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    facility_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ResidentSnapshot(SQLModel, table=True):
    """All structured resident data captured at one point in time."""

    __tablename__ = "resident_snapshot"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    resident_id: UUID | None = Field(
        default=None,
        foreign_key="resident.id",
        index=True,
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    current_weight: float | None = None
    weight_date: date | None = None
    bmi: float | None = None
    weight_history: list[WeightHistoryEntry] = Field(
        default_factory=list,
        sa_column=Column(
            _PydanticJSON(list[WeightHistoryEntry]),
            nullable=False,
        ),
    )
    medications: list[MedicationData] = Field(
        default_factory=list,
        sa_column=Column(_PydanticJSON(list[MedicationData]), nullable=False),
    )
    diet: str | None = None
    diet_texture: str | None = None
    liquid_consistency: str | None = None
    diet_restrictions: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    food_preferences: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    tubefeed_order: TubeFeedingData | None = Field(
        default=None,
        sa_column=Column(_PydanticJSON(TubeFeedingData), nullable=True),
    )
    latest_labs: list[LabResult] = Field(
        default_factory=list,
        sa_column=Column(_PydanticJSON(list[LabResult]), nullable=False),
    )
    latest_labs_date: date | None = None
    age: int | None = None
    gender: str | None = None
    height: float | None = None
    meal_intake: str | None = None
    fluid_intake: str | None = None
    appetite: str | None = None
    meal_assistance: str | None = None
    past_medical_history: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    supplements: list[SupplementData] = Field(
        default_factory=list,
        sa_column=Column(_PydanticJSON(list[SupplementData]), nullable=False),
    )
    allergies: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    wounds: list[WoundData] = Field(
        default_factory=list,
        sa_column=Column(_PydanticJSON(list[WoundData]), nullable=False),
    )
    edema: EdemaData = Field(
        default_factory=EdemaData,
        sa_column=Column(_PydanticJSON(EdemaData), nullable=False),
    )
    dialysis: bool | None = None
    dialysis_dry_weight: float | None = None
    dialysis_target_weight: float | None = None
    admission_date: date | None = None
    readmission_date: date | None = None

    def clinical_payload(self) -> dict[str, object]:
        """Return clinical fields without snapshot persistence metadata."""
        return self.model_dump(
            mode="json",
            exclude={"id", "resident_id", "created_at"},
        )

    def to_console(self) -> str:
        """Render the clinical snapshot as formatted JSON."""
        return self.model_dump_json(
            indent=2,
            exclude={"id", "resident_id", "created_at"},
        )


class ResidentSnapshotAssessment(SQLModel, table=True):
    """A generated assessment associated with one resident snapshot."""

    __tablename__ = "resident_snapshot_assessment"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    resident_snapshot_id: UUID = Field(
        foreign_key="resident_snapshot.id",
        index=True,
    )
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    model_name: str
