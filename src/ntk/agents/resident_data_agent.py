"""Agent for merging deterministic file extraction into resident context."""

from __future__ import annotations

import dataclasses
import json
import typing
from datetime import UTC, datetime

import logfire
from pydantic import TypeAdapter
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_core import to_jsonable_python

from ntk.database.db import get_session
from ntk.models.resident_data import (
    DataConflict,
    LabReportExtraction,
    OrderReportExtraction,
    ProgressNote,
    ResidentContext,
    SourcedValue,
    SourceReference,
    WeightVitalsExtraction,
    WoundReportExtraction,
)
from ntk.models.settings import SETTINGS
from ntk.models.sql.resident import (
    EdemaData,
    LabResult,
    MedicationData,
    Resident,
    SupplementData,
    TubeFeedingData,
    WeightHistoryEntry,
    WoundData,
)
from ntk.repositories import ResidentRepo
from ntk.services.document import DocumentExtractorService

if typing.TYPE_CHECKING:
    import pathlib

    from ntk.models.sql.resident import ResidentSnapshot


logfire.configure()
logfire.instrument_pydantic_ai()

RESIDENT_DATA_MODEL = "gpt-4.1-mini"
RESIDENT_DATA_INSTRUCTIONS = """
Build one ResidentContext from every file listed in the user prompt.

Workflow:
1. Use the deterministic extractor output provided in the prompt as already-read
   source data. Do not ask to inspect those files again.
2. Merge the deterministic ResidentContext, extractor output, and supplementary
   user context into one ResidentContext. Never write to a database.
3. Populate resident_info only when facility_id is explicitly present in current
   files or user context. Do not look up database values. The application will
   attach any matching database resident and previous snapshot after extraction.
   Facility ID will be of the format EN140175 or 14045.
4. Never invent source identifiers. Put current clinical facts in resident_snapshot.

Source rules:
- Deterministic file extractor results are the primary source. Preserve filename,
  extraction time, dates, units, and source references.
- Additional user context is supplementary. Use only explicit facts and do not
  attribute them to a file.
- A previous snapshot is historical comparison context only. Never copy an old
  value into the current snapshot unless a current file or user context confirms it.
- Put extracted PCC progress notes in progress_notes. Clinical events must be
  directly supported and include SourceReference entries whenever their source is
  a file. Record incompatible supported values in conflicts.
- Use missing_information for clinically relevant fields not found in any source.

Never infer or invent clinical facts. Preserve medication sigs, diagnoses, weights,
labs, diet wording, wounds, supplements, allergies, intake, and nutrition support
orders. Use null for missing scalar values and empty lists for missing collections.
For unknown-format files, use only facts stated in the provided raw extracted text.
""".strip()

_SUPPORTED_SUFFIXES = frozenset({".csv", ".pdf"})
_SUPPORTED_EXTRACTORS = frozenset(
    {
        "PccWeightHistoryExtractor",
        "PccProgressNotesExtractor",
        "PccLabResultsExtractor",
        "WoundReportExtractor",
        "PccOrderReportExtractor",
        "NutritionCareManualExtractor",
        "DietManualExtractor",
        "MiscExtractor",
    },
)
_WEIGHT_HISTORY_ADAPTER = TypeAdapter(list[WeightHistoryEntry])
_MEDICATIONS_ADAPTER = TypeAdapter(list[MedicationData])
_TUBEFEED_ADAPTER = TypeAdapter(TubeFeedingData | None)
_LABS_ADAPTER = TypeAdapter(list[LabResult])
_SUPPLEMENTS_ADAPTER = TypeAdapter(list[SupplementData])
_WOUNDS_ADAPTER = TypeAdapter(list[WoundData])
_EDEMA_ADAPTER = TypeAdapter(EdemaData)


@dataclasses.dataclass(frozen=True)
class ResidentFileSource:
    """One supplied file and its preselected deterministic extractor."""

    file_id: str
    filename: str
    path: pathlib.Path
    extractor_name: str


@dataclasses.dataclass
class ResidentDataDependencies:
    """Files and extraction service available to one agent run."""

    files: dict[str, ResidentFileSource]
    extractor_service: DocumentExtractorService
    extracted_files: dict[str, object] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class ScalarContextMerge:
    """One extracted scalar value to merge into resident context."""

    field_name: str
    current_value: object
    extracted_value: object
    setter: typing.Callable[[typing.Any], None]
    source: SourceReference


_provider = OpenAIProvider(api_key=SETTINGS.open_ai_api_key)
_model = OpenAIResponsesModel(RESIDENT_DATA_MODEL, provider=_provider)
resident_data_agent = Agent(
    _model,
    deps_type=ResidentDataDependencies,
    output_type=ResidentContext,
    instructions=RESIDENT_DATA_INSTRUCTIONS,
)


class ResidentDataAgent:
    """Run deterministic file extraction before the LLM merges resident context."""

    def __init__(
        self,
        agent: Agent[ResidentDataDependencies, ResidentContext] | None = None,
        extractor_service: DocumentExtractorService | None = None,
        resident_repo: ResidentRepo | None = None,
    ) -> None:
        """Initialize optional dependencies for production or testing."""
        self.agent = agent or resident_data_agent
        self.extractor_service = extractor_service or DocumentExtractorService()
        self.resident_repo = resident_repo or ResidentRepo(session=next(get_session()))

    async def extract(
        self,
        paths: list[pathlib.Path],
        context: str | None = None,
    ) -> ResidentContext:
        """Classify and extract files, then let the agent merge known facts."""
        dependencies = self._build_dependencies(paths)
        self.extract_files(dependencies)
        deterministic_context = self.build_deterministic_context(dependencies)
        prompt = self._build_prompt(dependencies, context, deterministic_context)
        resident_context = (await self.agent.run(prompt, deps=dependencies)).output
        self.normalize_context(resident_context)
        self.add_deterministic_context(resident_context, dependencies)
        self.add_database_context(resident_context)
        self.normalize_context(resident_context)
        return resident_context

    def extract_files(self, dependencies: ResidentDataDependencies) -> None:
        """Run every selected extractor once before the LLM sees the prompt."""
        for source in dependencies.files.values():
            if source.file_id in dependencies.extracted_files:
                continue
            dependencies.extracted_files[source.file_id] = (
                dependencies.extractor_service.extract_file(
                    source.path,
                    expected_extractor=source.extractor_name,
                )
            )

    def build_deterministic_context(
        self,
        dependencies: ResidentDataDependencies,
    ) -> ResidentContext:
        """Return context populated only from cached deterministic extraction."""
        resident_context = ResidentContext()
        self.add_deterministic_context(resident_context, dependencies)
        self.add_database_context(resident_context)
        self.normalize_context(resident_context)
        return resident_context

    def normalize_context(self, resident_context: ResidentContext) -> None:
        """Normalize nested SQL-model fields that may arrive as plain dicts."""
        self._normalize_snapshot(resident_context.resident_snapshot)
        if resident_context.previous_snapshot is not None:
            self._normalize_snapshot(resident_context.previous_snapshot)

    def add_deterministic_context(
        self,
        resident_context: ResidentContext,
        dependencies: ResidentDataDependencies,
    ) -> None:
        """Merge all cached deterministic extractor results into context."""
        self.add_progress_notes_context(resident_context, dependencies)
        self.add_weight_history_context(resident_context, dependencies)
        self.add_lab_results_context(resident_context, dependencies)
        self.add_order_report_context(resident_context, dependencies)
        self.add_wound_report_context(resident_context, dependencies)

    def add_progress_notes_context(
        self,
        resident_context: ResidentContext,
        dependencies: ResidentDataDependencies,
    ) -> None:
        """Attach progress notes extracted from PCC progress-note reports."""
        extracted_notes: list[ProgressNote] = []
        for source in dependencies.files.values():
            if source.extractor_name != "PccProgressNotesExtractor":
                continue
            extracted = dependencies.extracted_files.get(source.file_id)
            if extracted is None:
                extracted = dependencies.extractor_service.extract_file(
                    source.path,
                    expected_extractor=source.extractor_name,
                )
                dependencies.extracted_files[source.file_id] = extracted
            extracted_notes.extend(self._validated_progress_notes(extracted))
        if extracted_notes:
            resident_context.progress_notes = self._merge_progress_notes(
                resident_context.progress_notes,
                extracted_notes,
            )

    def add_weight_history_context(
        self,
        resident_context: ResidentContext,
        dependencies: ResidentDataDependencies,
    ) -> None:
        """Attach weights extracted from PCC weights-and-vitals reports."""
        weight_extractions: list[WeightVitalsExtraction] = []
        for source in dependencies.files.values():
            if source.extractor_name != "PccWeightHistoryExtractor":
                continue
            extracted = dependencies.extracted_files.get(source.file_id)
            if extracted is None:
                extracted = dependencies.extractor_service.extract_file(
                    source.path,
                    expected_extractor=source.extractor_name,
                )
                dependencies.extracted_files[source.file_id] = extracted
            weight_extractions.append(self._validated_weight_vitals(extracted))
        if not weight_extractions:
            return
        snapshot = resident_context.resident_snapshot
        for extraction in weight_extractions:
            self._add_facility_id_context(resident_context, extraction)
            self._add_scalar_context(
                resident_context,
                ScalarContextMerge(
                    field_name="resident_snapshot.height",
                    current_value=snapshot.height,
                    extracted_value=extraction.height,
                    setter=lambda value: setattr(snapshot, "height", value),
                    source=extraction.source,
                ),
            )
            self._add_scalar_context(
                resident_context,
                ScalarContextMerge(
                    field_name="resident_snapshot.age",
                    current_value=snapshot.age,
                    extracted_value=extraction.age,
                    setter=lambda value: setattr(snapshot, "age", value),
                    source=extraction.source,
                ),
            )
        snapshot.weight_history = self._merge_weight_history(
            snapshot.weight_history,
            [
                weight
                for extraction in weight_extractions
                for weight in extraction.weight_history
            ],
        )
        if not snapshot.weight_history:
            return
        latest_weight = snapshot.weight_history[0]
        latest_source = weight_extractions[0]
        self._add_scalar_context(
            resident_context,
            ScalarContextMerge(
                field_name="resident_snapshot.current_weight",
                current_value=snapshot.current_weight,
                extracted_value=latest_weight.weight_lb,
                setter=lambda value: setattr(snapshot, "current_weight", value),
                source=latest_source.source,
            ),
        )
        weight_date = (
            datetime.fromisoformat(latest_weight.date).date()
            if latest_weight.date
            else None
        )
        self._add_scalar_context(
            resident_context,
            ScalarContextMerge(
                field_name="resident_snapshot.weight_date",
                current_value=snapshot.weight_date,
                extracted_value=weight_date,
                setter=lambda value: setattr(snapshot, "weight_date", value),
                source=latest_source.source,
            ),
        )

    def add_order_report_context(
        self,
        resident_context: ResidentContext,
        dependencies: ResidentDataDependencies,
    ) -> None:
        """Attach order data extracted from PCC order listing reports."""
        order_extractions: list[OrderReportExtraction] = []
        for source in dependencies.files.values():
            if source.extractor_name != "PccOrderReportExtractor":
                continue
            extracted = dependencies.extracted_files.get(source.file_id)
            if extracted is None:
                extracted = dependencies.extractor_service.extract_file(
                    source.path,
                    expected_extractor=source.extractor_name,
                )
                dependencies.extracted_files[source.file_id] = extracted
            order_extractions.append(self._validated_order_report(extracted))
        if not order_extractions:
            return
        snapshot = resident_context.resident_snapshot
        for extraction in order_extractions:
            self._add_facility_id_from_source(
                resident_context,
                extraction.facility_id,
                extraction.source,
            )
            for field_name in ("diet", "diet_texture", "liquid_consistency"):
                self._add_scalar_context(
                    resident_context,
                    ScalarContextMerge(
                        field_name=f"resident_snapshot.{field_name}",
                        current_value=getattr(snapshot, field_name),
                        extracted_value=getattr(extraction, field_name),
                        setter=lambda value, name=field_name: setattr(
                            snapshot,
                            name,
                            value,
                        ),
                        source=extraction.source,
                    ),
                )
            self._add_scalar_context(
                resident_context,
                ScalarContextMerge(
                    field_name="resident_snapshot.tubefeed_order",
                    current_value=snapshot.tubefeed_order,
                    extracted_value=extraction.tubefeed_order,
                    setter=lambda value: setattr(snapshot, "tubefeed_order", value),
                    source=extraction.source,
                ),
            )
            snapshot.medications = self._merge_medications(
                snapshot.medications,
                extraction.medications,
            )
            snapshot.supplements = self._merge_supplements(
                snapshot.supplements,
                extraction.supplements,
            )

    def add_lab_results_context(
        self,
        resident_context: ResidentContext,
        dependencies: ResidentDataDependencies,
    ) -> None:
        """Attach latest labs extracted from PCC lab results reports."""
        lab_extractions: list[LabReportExtraction] = []
        for source in dependencies.files.values():
            if source.extractor_name != "PccLabResultsExtractor":
                continue
            extracted = dependencies.extracted_files.get(source.file_id)
            if extracted is None:
                extracted = dependencies.extractor_service.extract_file(
                    source.path,
                    expected_extractor=source.extractor_name,
                )
                dependencies.extracted_files[source.file_id] = extracted
            lab_extractions.append(self._validated_lab_report(extracted))
        latest_extraction = self._latest_lab_extraction(lab_extractions)
        if latest_extraction is None:
            return
        self._add_facility_id_from_source(
            resident_context,
            latest_extraction.facility_id,
            latest_extraction.source,
        )
        snapshot = resident_context.resident_snapshot
        latest_labs_date = (
            datetime.fromisoformat(latest_extraction.latest_labs_date).date()
            if latest_extraction.latest_labs_date
            else None
        )
        self._add_scalar_context(
            resident_context,
            ScalarContextMerge(
                field_name="resident_snapshot.latest_labs_date",
                current_value=snapshot.latest_labs_date,
                extracted_value=latest_labs_date,
                setter=lambda value: setattr(snapshot, "latest_labs_date", value),
                source=latest_extraction.source,
            ),
        )
        if snapshot.latest_labs_date == latest_labs_date:
            snapshot.latest_labs = self._merge_labs(
                snapshot.latest_labs,
                latest_extraction.latest_labs,
            )

    def add_wound_report_context(
        self,
        resident_context: ResidentContext,
        dependencies: ResidentDataDependencies,
    ) -> None:
        """Attach wounds for the current resident from wound reports."""
        if resident_context.resident_info is None:
            return
        facility_id = resident_context.resident_info.facility_id
        wound_extractions: list[WoundReportExtraction] = []
        for source in dependencies.files.values():
            if source.extractor_name != "WoundReportExtractor":
                continue
            extracted = dependencies.extracted_files.get(source.file_id)
            if extracted is None:
                extracted = dependencies.extractor_service.extract_file(
                    source.path,
                    expected_extractor=source.extractor_name,
                )
                dependencies.extracted_files[source.file_id] = extracted
            wound_extractions.append(self._validated_wound_report(extracted))
        current_wounds = [
            wound
            for extraction in wound_extractions
            for resident in extraction.residents
            if resident.facility_id == facility_id
            for wound in resident.wounds
        ]
        if current_wounds:
            resident_context.resident_snapshot.wounds = self._merge_wounds(
                resident_context.resident_snapshot.wounds,
                current_wounds,
            )

    def add_database_context(self, resident_context: ResidentContext) -> None:
        """Attach deterministic database context after file extraction."""
        if resident_context.resident_info is None:
            return
        facility_id = resident_context.resident_info.facility_id
        resident = self.resident_repo.get_by_facility_id(facility_id)
        if resident is None:
            return
        resident_context.resident_info = resident
        resident_context.resident_snapshot.resident_id = resident.id
        resident_context.previous_snapshot = self.get_last_known_snapshot(facility_id)
        resident_context.latest_nutrition_assessment = (
            self.get_latest_nutrition_assessment(resident_context.progress_notes)
        )

    def get_last_known_snapshot(self, facility_id: str) -> ResidentSnapshot | None:
        """Return the latest persisted snapshot for a facility resident id."""
        resident = self.resident_repo.get_by_facility_id(facility_id)
        if resident is None:
            return None
        return self.resident_repo.get_latest_snapshot(resident.id)

    @staticmethod
    def get_latest_nutrition_assessment(
        notes: list[ProgressNote],
    ) -> ProgressNote | None:
        """Return the most recent nutrition-related progress note."""
        nutrition_notes = [
            note for note in notes if ResidentDataAgent._is_nutrition_note(note)
        ]
        if not nutrition_notes:
            return None
        return max(
            nutrition_notes,
            key=lambda note: note.note_date or datetime.min.replace(tzinfo=UTC),
        )

    def _build_dependencies(
        self,
        paths: list[pathlib.Path],
    ) -> ResidentDataDependencies:
        if not paths:
            msg = "At least one PDF or CSV file is required"
            raise ValueError(msg)
        sources: dict[str, ResidentFileSource] = {}
        for index, path in enumerate(paths, start=1):
            self._validate_file(path)
            extractor_name = self.extractor_service.get_extractor_name(path)
            if extractor_name not in _SUPPORTED_EXTRACTORS:
                msg = f"No resident extraction support maps to {extractor_name}"
                raise RuntimeError(msg)
            file_id = f"file_{index}"
            sources[file_id] = ResidentFileSource(
                file_id=file_id,
                filename=path.name,
                path=path,
                extractor_name=extractor_name,
            )
        return ResidentDataDependencies(
            files=sources,
            extractor_service=self.extractor_service,
        )

    @staticmethod
    def _build_prompt(
        dependencies: ResidentDataDependencies,
        context: str | None,
        deterministic_context: ResidentContext,
    ) -> str:
        manifest = "\n".join(
            f"- {source.file_id}: filename={source.filename!r}; "
            f"extractor={source.extractor_name}"
            for source in dependencies.files.values()
        )
        extracted_payload = ResidentDataAgent._serialized_extractions(dependencies)
        sections = [
            RESIDENT_DATA_INSTRUCTIONS,
            "Files already extracted before this run:\n" + manifest,
            "Deterministic ResidentContext to preserve and reconcile:\n"
            + deterministic_context.to_console(),
            "Raw deterministic extractor output by file_id:\n"
            + json.dumps(extracted_payload, indent=2, default=str),
        ]
        if context and context.strip():
            sections.append(
                "Supplementary user context (not file-derived):\n" + context.strip(),
            )
        return "\n\n".join(sections)

    @staticmethod
    def _serialized_extractions(
        dependencies: ResidentDataDependencies,
    ) -> dict[str, object]:
        return {
            file_id: {
                "filename": source.filename,
                "extractor": source.extractor_name,
                "data": to_jsonable_python(
                    dependencies.extracted_files.get(file_id),
                ),
            }
            for file_id, source in dependencies.files.items()
        }

    @staticmethod
    def _validate_file(path: pathlib.Path) -> None:
        if not path.is_file():
            msg = f"Resident data file does not exist: {path}"
            raise ValueError(msg)
        if path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            msg = f"Path is not a PDF or CSV file: {path}"
            raise ValueError(msg)
        if path.stat().st_size == 0:
            msg = f"Resident data file is empty: {path}"
            raise ValueError(msg)

    @staticmethod
    def _is_nutrition_note(note: ProgressNote) -> bool:
        note_type = note.note_type.casefold() if note.note_type else ""
        return "nutrition" in note_type or "dietician" in note_type

    @staticmethod
    def _validated_progress_notes(extracted: object) -> list[ProgressNote]:
        if not isinstance(extracted, list) or not all(
            isinstance(note, ProgressNote) for note in extracted
        ):
            msg = "PCC progress notes extractor must return a list of ProgressNote"
            raise TypeError(msg)
        return extracted

    @staticmethod
    def _validated_weight_vitals(extracted: object) -> WeightVitalsExtraction:
        if not isinstance(extracted, WeightVitalsExtraction):
            msg = "PCC weight-history extractor must return a WeightVitalsExtraction"
            raise TypeError(msg)
        return extracted

    @staticmethod
    def _validated_order_report(extracted: object) -> OrderReportExtraction:
        if not isinstance(extracted, OrderReportExtraction):
            msg = "PCC order report extractor must return an OrderReportExtraction"
            raise TypeError(msg)
        return extracted

    @staticmethod
    def _validated_lab_report(extracted: object) -> LabReportExtraction:
        if not isinstance(extracted, LabReportExtraction):
            msg = "PCC lab results extractor must return a LabReportExtraction"
            raise TypeError(msg)
        return extracted

    @staticmethod
    def _validated_wound_report(extracted: object) -> WoundReportExtraction:
        if not isinstance(extracted, WoundReportExtraction):
            msg = "Wound report extractor must return a WoundReportExtraction"
            raise TypeError(msg)
        return extracted

    @staticmethod
    def _latest_lab_extraction(
        lab_extractions: list[LabReportExtraction],
    ) -> LabReportExtraction | None:
        dated_extractions = [
            extraction
            for extraction in lab_extractions
            if extraction.latest_labs_date is not None
        ]
        if not dated_extractions:
            return None
        return max(
            dated_extractions,
            key=lambda extraction: extraction.latest_labs_date or "",
        )

    @staticmethod
    def _merge_progress_notes(
        current_notes: list[ProgressNote],
        extracted_notes: list[ProgressNote],
    ) -> list[ProgressNote]:
        merged = list(current_notes)
        seen = {ResidentDataAgent._progress_note_key(note) for note in current_notes}
        for note in extracted_notes:
            key = ResidentDataAgent._progress_note_key(note)
            if key in seen:
                continue
            merged.append(note)
            seen.add(key)
        return merged

    @staticmethod
    def _merge_weight_history(
        current_weights: list[WeightHistoryEntry],
        extracted_weights: list[WeightHistoryEntry],
    ) -> list[WeightHistoryEntry]:
        merged = list(current_weights)
        seen = {ResidentDataAgent._weight_history_key(weight) for weight in merged}
        for weight in extracted_weights:
            key = ResidentDataAgent._weight_history_key(weight)
            # if wt pulled from current documents is same as wt in db snapshot skip
            if key in seen:
                continue
            merged.append(weight)
            seen.add(key)
        return sorted(
            merged,
            key=lambda weight: weight.date or "",
            reverse=True,
        )

    @staticmethod
    def _progress_note_key(note: ProgressNote) -> tuple[object, ...]:
        return (
            note.source.source_name,
            note.source.page_start,
            note.source.page_end,
            note.note_date,
            note.note_type,
            note.note_text,
        )

    @staticmethod
    def _weight_history_key(weight: WeightHistoryEntry) -> tuple[object, ...]:
        return (weight.date, weight.weight_lb, weight.description)

    @staticmethod
    def _merge_medications(
        current_medications: list[MedicationData],
        extracted_medications: list[MedicationData],
    ) -> list[MedicationData]:
        merged = list(current_medications)
        seen = {ResidentDataAgent._medication_key(medication) for medication in merged}
        for medication in extracted_medications:
            key = ResidentDataAgent._medication_key(medication)
            if key in seen:
                continue
            merged.append(medication)
            seen.add(key)
        return merged

    @staticmethod
    def _merge_supplements(
        current_supplements: list[SupplementData],
        extracted_supplements: list[SupplementData],
    ) -> list[SupplementData]:
        merged = list(current_supplements)
        seen = {ResidentDataAgent._supplement_key(supplement) for supplement in merged}
        for supplement in extracted_supplements:
            key = ResidentDataAgent._supplement_key(supplement)
            if key in seen:
                continue
            merged.append(supplement)
            seen.add(key)
        return merged

    @staticmethod
    def _merge_labs(
        current_labs: list[LabResult],
        extracted_labs: list[LabResult],
    ) -> list[LabResult]:
        merged = list(current_labs)
        seen = {ResidentDataAgent._lab_key(lab) for lab in merged}
        for lab in extracted_labs:
            key = ResidentDataAgent._lab_key(lab)
            if key in seen:
                continue
            merged.append(lab)
            seen.add(key)
        return merged

    @staticmethod
    def _merge_wounds(
        current_wounds: list[WoundData],
        extracted_wounds: list[WoundData],
    ) -> list[WoundData]:
        merged = list(current_wounds)
        seen = {ResidentDataAgent._wound_key(wound) for wound in merged}
        for wound in extracted_wounds:
            key = ResidentDataAgent._wound_key(wound)
            if key in seen:
                continue
            merged.append(wound)
            seen.add(key)
        return merged

    @staticmethod
    def _add_facility_id_context(
        resident_context: ResidentContext,
        extraction: WeightVitalsExtraction,
    ) -> None:
        ResidentDataAgent._add_facility_id_from_source(
            resident_context,
            extraction.facility_id,
            extraction.source,
        )

    @staticmethod
    def _add_facility_id_from_source(
        resident_context: ResidentContext,
        facility_id: str | None,
        source: SourceReference,
    ) -> None:
        if facility_id is None:
            return
        if resident_context.resident_info is None:
            resident_context.resident_info = Resident(
                facility_id=facility_id,
            )
            return
        resident = resident_context.resident_info
        ResidentDataAgent._add_scalar_context(
            resident_context,
            ScalarContextMerge(
                field_name="resident_info.facility_id",
                current_value=resident.facility_id,
                extracted_value=facility_id,
                setter=lambda value: setattr(
                    resident,
                    "facility_id",
                    value,
                ),
                source=source,
            ),
        )

    @staticmethod
    def _add_scalar_context(
        resident_context: ResidentContext,
        merge: ScalarContextMerge,
    ) -> None:
        if merge.extracted_value is None:
            return
        if merge.current_value is None:
            merge.setter(merge.extracted_value)
            return
        if ResidentDataAgent._values_match(merge.current_value, merge.extracted_value):
            return
        resident_context.conflicts.append(
            DataConflict(
                field=merge.field_name,
                values=[
                    SourcedValue(value=merge.current_value),
                    SourcedValue(
                        value=merge.extracted_value,
                        sources=[merge.source],
                    ),
                ],
                explanation=(
                    f"Existing {merge.field_name} did not match value extracted "
                    f"from {merge.source.source_name}"
                ),
            ),
        )

    @staticmethod
    def _values_match(left: object, right: object) -> bool:
        if isinstance(left, float | int) and isinstance(right, float | int):
            return float(left) == float(right)
        return left == right

    @staticmethod
    def _medication_key(medication: MedicationData) -> tuple[object, ...]:
        return (
            medication.name.casefold(),
            medication.dose,
            medication.route,
            medication.frequency,
        )

    @staticmethod
    def _supplement_key(supplement: SupplementData) -> tuple[object, ...]:
        return (
            supplement.name.casefold(),
            supplement.amount,
            supplement.frequency,
        )

    @staticmethod
    def _lab_key(lab: LabResult) -> tuple[object, ...]:
        return (
            lab.name.casefold(),
            lab.value,
            lab.unit,
            lab.date,
        )

    @staticmethod
    def _wound_key(wound: WoundData) -> tuple[object, ...]:
        return (
            wound.type.casefold(),
            wound.location.casefold(),
            wound.weeks_in_treatment,
            wound.stage,
            wound.progress,
        )

    @staticmethod
    def _normalize_snapshot(snapshot: ResidentSnapshot) -> None:
        snapshot.weight_history = _WEIGHT_HISTORY_ADAPTER.validate_python(
            snapshot.weight_history,
        )
        snapshot.medications = _MEDICATIONS_ADAPTER.validate_python(
            snapshot.medications,
        )
        snapshot.tubefeed_order = _TUBEFEED_ADAPTER.validate_python(
            snapshot.tubefeed_order,
        )
        snapshot.latest_labs = _LABS_ADAPTER.validate_python(snapshot.latest_labs)
        snapshot.supplements = _SUPPLEMENTS_ADAPTER.validate_python(
            snapshot.supplements,
        )
        snapshot.wounds = _WOUNDS_ADAPTER.validate_python(snapshot.wounds)
        snapshot.edema = _EDEMA_ADAPTER.validate_python(snapshot.edema)
