"""SQL models for residents and their nutrition assessment snapshots."""

from __future__ import annotations

import typing
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, TypeAdapter
from pydantic import Field as PydanticField
from sqlalchemy import JSON, Column
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, Relationship, SQLModel

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.engine.interfaces import Dialect

_ResidentModelT = typing.TypeVar("_ResidentModelT", bound=BaseModel)


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


class PccWeightVitalsExtraction(BaseModel):
    admission_date: date | None = None
    height: float | None = None
    facility_id: str | None = None
    weight_history: list[WeightHistoryEntry] = Field(default_factory=list)
    source: SourceReference | None = None


class PccProgressNotesExtraction(BaseModel):
    """Structured facts extracted from a PCC progress notes report."""

    facility_id: str | None = None
    gender: str | None = None
    admission_date: str | None = None
    age: int | None = None
    allergies: list[str] = Field(default_factory=list)
    diagnoses: list[str] = Field(default_factory=list)
    progress_notes: list[ProgressNote] = Field(default_factory=list)
    source: SourceReference | None = None


class PccOrderReportExtraction(BaseModel):
    """Structured facts extracted from a PCC order listing report."""

    facility_id: str | None = None
    orders: list[PccOrder] = Field(default_factory=list)
    source: SourceReference | None = None


class PccLabReportExtraction(BaseModel):
    """Structured facts extracted from a PCC lab results report."""

    facility_id: str | None = None
    admission_date: date | None = None
    age: int | None = None
    lab_results: list[LabResult] = Field(default_factory=list)
    source: SourceReference | None = None


class CsvWoundReportExtraction(BaseModel):
    """Structured facts extracted from a wound report."""

    facility_id: str | None = None
    wounds: list[Wound] = Field(default_factory=list)
    source: SourceReference | None = None


ResidentExtraction: typing.TypeAlias = (
    PccWeightVitalsExtraction
    | PccProgressNotesExtraction
    | PccOrderReportExtraction
    | PccLabReportExtraction
    | CsvWoundReportExtraction
)


class SourceReference(BaseModel):
    source_type: str
    extracted_at: datetime
    source: str | None = None


class PccOrder(BaseModel):
    """One row from a PCC order listing report."""

    summary: str
    category: str | None = None
    status: str | None = None
    revision_date: date | None = None
    supply_last_order_date: date | None = None
    supply_reorder: str | None = None


class ProgressNote(BaseModel):
    note_date: datetime | None = None
    note_type: str | None = None
    author: str | None = None
    note_text: str
    source: SourceReference
    raw_text: str


class WeightHistoryEntry(BaseModel):
    """One dated or described historical weight."""

    date: str | None = None
    weight_lb: float | None = None
    description: str | None = None


class LabResult(BaseModel):
    """One laboratory result represented by the source."""

    name: str
    result: str | None = None
    unit: str | None = None
    flag: str | None = None
    reference_range: str | None = None
    date: datetime | None = None


class Wound(BaseModel):
    """Skin integrity and wound information."""

    type: str
    location: str
    weeks_in_treatment: int | None = None
    progress: str | None = None
    stage: str | None = None
    size: str | None = None
    assessment_note: str | None = None
    physician_orders: str | None = None
    physician_orders_notes: str | None = None


class EdemaData(BaseModel):
    """Presence, location, and severity of edema."""

    present: bool | None = None
    locations: list[str] = PydanticField(default_factory=list)
    severity: str | None = None


class DialysisData(BaseModel):
    type: str | None = None
    schedule: str | None = None
    chair_time: str | None = None
    location: str | None = None
    dry_weight: float | None = None
    target_weight: float | None = None


class SourcedValue(BaseModel):
    value: typing.Any
    observed_at: datetime | None = None
    sources: list[SourceReference] = Field(default_factory=list)


class DataConflict(BaseModel):
    field: str
    values: list[SourcedValue]
    explanation: str


class Resident(SQLModel, table=True):
    """A resident belonging to one facility."""

    __tablename__ = "resident"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    facility_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    snapshot: ResidentSnapshot = Relationship(back_populates="resident")


class ResidentSnapshotBase(SQLModel):
    """All structured resident data captured at one point in time."""

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    weight_history: list[WeightHistoryEntry] = Field(
        default_factory=list,
        sa_column=Column(
            _PydanticJSON(list[WeightHistoryEntry]),
            nullable=False,
        ),
    )
    labs: list[LabResult] = Field(
        default_factory=list,
        sa_column=Column(_PydanticJSON(list[LabResult]), nullable=False),
    )
    admission_date: date | None = None
    age: int | None = None
    gender: str | None = None
    height: float | None = None
    diagnoses: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    orders: list[PccOrder] = Field(
        default_factory=list,
        sa_column=Column(_PydanticJSON(list[PccOrder]), nullable=False),
    )
    allergies: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    wounds: list[Wound] = Field(
        default_factory=list,
        sa_column=Column(_PydanticJSON(list[Wound]), nullable=False),
    )
    # the bottom ones should be retrieved from progress notes
    diet: str | None = None
    meal_intake: str | None = None
    fluid_intake: str | None = None
    appetite: str | None = None
    meal_assistance: str | None = None
    food_preferences: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    diet_restrictions: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    edema: EdemaData = Field(
        default_factory=EdemaData,
        sa_column=Column(_PydanticJSON(EdemaData), nullable=False),
    )
    dialysis: DialysisData = Field(
        default_factory=DialysisData,
        sa_column=Column(_PydanticJSON(DialysisData), nullable=False),
    )
    readmission_date: date | None = None


class ResidentSnapshot(ResidentSnapshotBase, table=True):
    """All structured resident data captured at one point in time."""

    __tablename__ = "resident_snapshot"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    resident_id: UUID | None = Field(
        default=None,
        foreign_key="resident.id",
        index=True,
    )
    resident: Resident = Relationship(
        back_populates="snapshot",
    )


class ResidentContext(ResidentSnapshotBase):
    """Combined resident facts assembled from document extractions and the agent."""

    facility_id: str | None = None
    resident_id: str | None = None
    progress_notes: list[ProgressNote] = Field(default_factory=list)
    conflicts: list[DataConflict] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)

    def merge_extraction(
        self,
        extraction: ResidentExtraction,
        *,
        prefer_extracted: bool = False,
    ) -> None:
        """Merge one supported deterministic extraction into this context."""
        if not isinstance(
            extraction,
            (
                PccWeightVitalsExtraction,
                PccProgressNotesExtraction,
                PccOrderReportExtraction,
                PccLabReportExtraction,
                CsvWoundReportExtraction,
            ),
        ):
            msg = f"Unsupported resident extraction: {type(extraction).__name__}"
            raise TypeError(msg)

        self._merge_scalar(
            "facility_id",
            extraction.facility_id,
            extraction.source,
            prefer_extracted=prefer_extracted,
        )
        if isinstance(extraction, PccWeightVitalsExtraction):
            self._merge_scalar(
                "admission_date",
                extraction.admission_date,
                extraction.source,
                prefer_extracted=prefer_extracted,
            )
            self._merge_scalar(
                "height",
                extraction.height,
                extraction.source,
                prefer_extracted=prefer_extracted,
            )
            self.weight_history = self._merge_unique(
                self.weight_history,
                extraction.weight_history,
            )
            self.weight_history.sort(
                key=lambda weight: weight.date or "",
                reverse=True,
            )
            return
        if isinstance(extraction, PccProgressNotesExtraction):
            self._merge_scalar(
                "admission_date",
                self._date_from_iso(extraction.admission_date),
                extraction.source,
                prefer_extracted=prefer_extracted,
            )
            self._merge_scalar(
                "gender",
                extraction.gender,
                extraction.source,
                prefer_extracted=prefer_extracted,
            )
            self._merge_scalar(
                "age",
                extraction.age,
                extraction.source,
                prefer_extracted=prefer_extracted,
            )
            self.allergies = self._merge_strings(
                self.allergies,
                extraction.allergies,
            )
            self.diagnoses = self._merge_strings(
                self.diagnoses,
                extraction.diagnoses,
            )
            self.progress_notes = self._merge_unique(
                self.progress_notes,
                extraction.progress_notes,
            )
            return
        if isinstance(extraction, PccOrderReportExtraction):
            self.orders = self._merge_unique(self.orders, extraction.orders)
            return
        if isinstance(extraction, PccLabReportExtraction):
            self._merge_scalar(
                "admission_date",
                extraction.admission_date,
                extraction.source,
                prefer_extracted=prefer_extracted,
            )
            self._merge_scalar(
                "age",
                extraction.age,
                extraction.source,
                prefer_extracted=prefer_extracted,
            )
            self.labs = self._merge_unique(self.labs, extraction.lab_results)
            return
        self.wounds = self._merge_unique(self.wounds, extraction.wounds)

    def merge_extractions(
        self,
        extractions: Iterable[ResidentExtraction],
        *,
        prefer_extracted: bool = False,
    ) -> None:
        """Merge a sequence of deterministic extractions into this context."""
        for extraction in extractions:
            self.merge_extraction(
                extraction,
                prefer_extracted=prefer_extracted,
            )

    def _merge_scalar(
        self,
        field_name: str,
        extracted_value: object | None,
        source: SourceReference | None,
        *,
        prefer_extracted: bool,
    ) -> None:
        if extracted_value is None:
            return
        current_value = getattr(self, field_name)
        if current_value is None:
            setattr(self, field_name, extracted_value)
            return
        if self._values_match(current_value, extracted_value):
            return
        conflict = DataConflict(
            field=field_name,
            values=[
                SourcedValue(value=current_value),
                SourcedValue(
                    value=extracted_value,
                    observed_at=source.extracted_at if source else None,
                    sources=[source] if source else [],
                ),
            ],
            explanation=self._conflict_explanation(field_name, source),
        )
        if conflict not in self.conflicts:
            self.conflicts.append(conflict)
        if prefer_extracted:
            setattr(self, field_name, extracted_value)

    @staticmethod
    def _merge_unique(
        current: list[_ResidentModelT],
        extracted: list[_ResidentModelT],
    ) -> list[_ResidentModelT]:
        merged = list(current)
        seen = {item.model_dump_json() for item in merged}
        for item in extracted:
            key = item.model_dump_json()
            if key not in seen:
                merged.append(item)
                seen.add(key)
        return merged

    @staticmethod
    def _merge_strings(current: list[str], extracted: list[str]) -> list[str]:
        merged = list(current)
        seen = {value.casefold() for value in merged}
        for value in extracted:
            normalized = " ".join(value.split())
            if normalized and normalized.casefold() not in seen:
                merged.append(normalized)
                seen.add(normalized.casefold())
        return merged

    @staticmethod
    def _date_from_iso(value: str | None) -> date | None:
        if value is None:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _values_match(left: object, right: object) -> bool:
        if isinstance(left, int | float) and isinstance(right, int | float):
            return float(left) == float(right)
        if isinstance(left, str) and isinstance(right, str):
            return left.casefold() == right.casefold()
        return left == right

    @staticmethod
    def _conflict_explanation(
        field_name: str,
        source: SourceReference | None,
    ) -> str:
        source_name = (
            source.source if source and source.source else "another extraction"
        )
        return f"Existing {field_name} conflicts with the value from {source_name}"

    def clinical_payload(self) -> dict[str, object]:
        """Return clinical fields without snapshot persistence metadata."""
        return self.model_dump(
            mode="json",
            exclude={"id", "resident_id", "created_at"},
        )

    def summary(self) -> str:
        """Return concise, deidentified clinical text for semantic retrieval."""
        resident = self._summary_section(
            "Resident",
            (
                f"{self.age}-year-old" if self.age is not None else None,
                self.gender,
                f"admitted {self.admission_date}" if self.admission_date else None,
                f"readmitted {self.readmission_date}"
                if self.readmission_date
                else None,
                f"height {self.height:g} in" if self.height is not None else None,
            ),
        )
        nutrition = self._summary_section(
            "Nutrition",
            (
                f"diet {self.diet}" if self.diet else None,
                f"meal intake {self.meal_intake}" if self.meal_intake else None,
                f"fluid intake {self.fluid_intake}" if self.fluid_intake else None,
                f"appetite {self.appetite}" if self.appetite else None,
                f"meal assistance {self.meal_assistance}"
                if self.meal_assistance
                else None,
                f"preferences {', '.join(self.food_preferences)}"
                if self.food_preferences
                else None,
                f"restrictions {', '.join(self.diet_restrictions)}"
                if self.diet_restrictions
                else None,
            ),
        )
        weights = self._summary_section(
            "Recent weights",
            (
                self._weight_summary(weight)
                for weight in sorted(
                    self.weight_history,
                    key=lambda item: item.date or "",
                    reverse=True,
                )[:6]
            ),
        )
        labs = self._summary_section(
            "Recent labs",
            (
                self._lab_summary(lab)
                for lab in sorted(
                    self.labs,
                    key=lambda item: item.date.isoformat() if item.date else "",
                    reverse=True,
                )[:12]
            ),
        )
        orders = self._summary_section(
            "Orders",
            (self._order_summary(order) for order in self.orders[:12]),
        )
        wounds = self._summary_section(
            "Wounds",
            (self._wound_summary(wound) for wound in self.wounds[:8]),
        )
        dialysis = self._summary_section(
            "Dialysis",
            (
                self.dialysis.type,
                self.dialysis.schedule,
                f"chair time {self.dialysis.chair_time}"
                if self.dialysis.chair_time
                else None,
                f"location {self.dialysis.location}"
                if self.dialysis.location
                else None,
                f"dry weight {self.dialysis.dry_weight:g}"
                if self.dialysis.dry_weight is not None
                else None,
                f"target weight {self.dialysis.target_weight:g}"
                if self.dialysis.target_weight is not None
                else None,
            ),
        )
        edema = self._summary_section(
            "Edema",
            (
                "present"
                if self.edema.present is True
                else "absent"
                if self.edema.present is False
                else None,
                ", ".join(self.edema.locations) if self.edema.locations else None,
                self.edema.severity,
            ),
        )
        sections = (
            resident,
            self._summary_section("Diagnoses", self.diagnoses),
            self._summary_section("Allergies", self.allergies),
            nutrition,
            weights,
            labs,
            orders,
            wounds,
            dialysis,
            edema,
        )
        summary = "\n".join(section for section in sections if section)
        return summary or "No clinical resident data available."

    @staticmethod
    def _summary_section(label: str, values: Iterable[str | None]) -> str | None:
        cleaned = [" ".join(value.split()) for value in values if value]
        return f"{label}: {'; '.join(cleaned)}" if cleaned else None

    @staticmethod
    def _weight_summary(weight: WeightHistoryEntry) -> str | None:
        if weight.weight_lb is None:
            return None
        date_text = f"{weight.date}: " if weight.date else ""
        description = f" ({weight.description})" if weight.description else ""
        return f"{date_text}{weight.weight_lb:g} lb{description}"

    @staticmethod
    def _lab_summary(lab: LabResult) -> str:
        date_text = f"{lab.date.date()}: " if lab.date else ""
        value = " ".join(part for part in (lab.result, lab.unit) if part)
        flag = f" [{lab.flag}]" if lab.flag else ""
        reference = f" (reference {lab.reference_range})" if lab.reference_range else ""
        return f"{date_text}{lab.name} {value}{flag}{reference}".strip()

    @staticmethod
    def _order_summary(order: PccOrder) -> str:
        details = ", ".join(value for value in (order.category, order.status) if value)
        return f"{order.summary} [{details}]" if details else order.summary

    @staticmethod
    def _wound_summary(wound: Wound) -> str:
        stage = f"Stage {wound.stage} " if wound.stage else ""
        details = ", ".join(value for value in (wound.progress, wound.size) if value)
        suffix = f" ({details})" if details else ""
        return f"{stage}{wound.type} at {wound.location}{suffix}"


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
