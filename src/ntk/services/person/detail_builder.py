"""Build complete person details and deterministic clinical calculations."""

from __future__ import annotations

import typing
from datetime import UTC, date, datetime

from pydantic import TypeAdapter, ValidationError

from ntk.models.person_detail import (
    AnthropometricCalculations,
    ClinicalConflict,
    DerivedPersonCalculations,
    NutritionNeedsCalculation,
    ParenteralNutritionCalculation,
    PersonDetail,
    TubeFeedCalculation,
    WeightChangeDetail,
)
from ntk.models.sql.clinical import (
    ClinicalStatus,
    NutritionGoalType,
    PersonAllergy,
    PersonDialysis,
    PersonEnteralFeeding,
    PersonMedication,
    PersonNutritionGoal,
    PersonParenteralNutrition,
    PersonWeight,
)
from ntk.services.calculators.nutrition_calculator import (
    EnergyNeedsInput,
    Gender,
    Goal,
    NutritionCalculator,
)
from ntk.services.calculators.parenteral_nutrition_calculator import (
    ParenteralNutritionCalculator,
)
from ntk.services.calculators.weight_history_calculator import WeightHistoryCalculator
from ntk.utils.convert import Convert

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from ntk.models.sql.person import Person
    from ntk.repositories.person_repo import PersonAssessmentRecords
    from ntk.services.calculators.tubefeed_calculator import TubeFeedCalculator


_DATETIME_ADAPTER = TypeAdapter(datetime)
_DATE_ADAPTER = TypeAdapter(date)
_ClinicalRecordT = typing.TypeVar("_ClinicalRecordT")
_RecordT = typing.TypeVar("_RecordT")


class PersonDetailBuilder:
    """Select clinical state and calculate every derivable person detail."""

    def __init__(
        self,
        tube_feed_calculator: TubeFeedCalculator | None = None,
        parenteral_nutrition_calculator: ParenteralNutritionCalculator | None = None,
    ) -> None:
        """Accept calculators whose repositories or configuration are injected."""
        self.tube_feed_calculator = tube_feed_calculator
        self.parenteral_nutrition_calculator = (
            parenteral_nutrition_calculator or ParenteralNutritionCalculator()
        )

    def build(
        self,
        person: Person,
        records: PersonAssessmentRecords,
        *,
        on_date: date | None = None,
    ) -> PersonDetail:
        """Build a complete agent-facing snapshot from persisted person records."""
        effective_date = on_date or datetime.now(UTC).date()
        conflicts: list[ClinicalConflict] = []
        current_diet = self._singleton("diet", records.diets, conflicts)
        current_enteral_feeding = self._singleton(
            "enteral_feeding",
            records.enteral_feedings,
            conflicts,
        )
        current_parenteral_nutrition = self._singleton(
            "parenteral_nutrition",
            records.parenteral_nutrition_records,
            conflicts,
        )
        current_fluid_plan = self._singleton(
            "fluid_plan",
            records.fluid_plans,
            conflicts,
        )
        current_dialysis = self._singleton(
            "dialysis",
            records.dialysis_records,
            conflicts,
        )
        current_oral_feeding_status = self._singleton(
            "oral_feeding_status",
            records.oral_feeding_status_history,
            conflicts,
        )
        active_nutrition_goals = self._current_by_key(
            "nutrition_goal",
            records.nutrition_goals,
            lambda record: record.goal_type.value,
            conflicts,
        )
        current_weight_goal = self._current_weight_goal(
            active_nutrition_goals,
            conflicts,
        )
        active_diagnoses = self._current_by_key(
            "diagnosis",
            records.diagnoses,
            lambda record: record.diagnosis.casefold(),
            conflicts,
        )
        active_medications = self._active_medications(records.medications)
        active_supplements = self._current_by_key(
            "supplement",
            records.supplements,
            lambda record: record.product_name.casefold(),
            conflicts,
        )
        active_food_preferences = self._current_by_key(
            "food_preference",
            records.food_preferences,
            lambda record: f"{record.preference_type.value}|{record.item.casefold()}",
            conflicts,
        )
        active_misc_orders = self._active(records.misc_orders)
        ordered_weights = self._ordered_weights(records.weights)
        current_weight = next(
            (
                weight
                for weight in ordered_weights
                if self._measurement_datetime(weight) is not None
                and weight.weight_lb > 0
            ),
            None,
        )
        birth_date = self._as_date(person.date_of_birth)
        age = self._calculate_age(birth_date, effective_date)
        derived_calculations = self._calculate_details(
            person=person,
            effective_date=effective_date,
            age=age,
            current_weight=current_weight,
            weights=ordered_weights,
            current_weight_goal=current_weight_goal,
            current_dialysis=current_dialysis,
            current_enteral_feeding=current_enteral_feeding,
            current_parenteral_nutrition=current_parenteral_nutrition,
            conflicts=conflicts,
        )
        return PersonDetail(
            person_id=person.id,
            name=person.name,
            first_name=person.first_name,
            last_name=person.last_name,
            date_of_birth=birth_date,
            age=age,
            sex=person.sex,
            height_in=person.height_in,
            facility_id=person.facility_id,
            facility=person.facility,
            person_identifier=person.person_identifier,
            current_weight=current_weight,
            current_diet=current_diet,
            current_enteral_feeding=current_enteral_feeding,
            current_parenteral_nutrition=current_parenteral_nutrition,
            current_fluid_plan=current_fluid_plan,
            current_dialysis=current_dialysis,
            current_oral_feeding_status=current_oral_feeding_status,
            current_weight_goal=current_weight_goal,
            active_nutrition_goals=active_nutrition_goals,
            active_diagnoses=active_diagnoses,
            active_allergies=self._allergies(records.allergies),
            active_medications=active_medications,
            active_supplements=active_supplements,
            active_food_preferences=active_food_preferences,
            active_misc_orders=active_misc_orders,
            weights=ordered_weights,
            labs=self._ordered_records(records.labs),
            diagnoses=self._ordered_records(records.diagnoses),
            allergies=self._ordered_records(records.allergies),
            medications=self._ordered_records(records.medications),
            diets=self._ordered_records(records.diets),
            enteral_feedings=self._ordered_records(records.enteral_feedings),
            parenteral_nutrition_records=self._ordered_records(
                records.parenteral_nutrition_records,
            ),
            fluid_plans=self._ordered_records(records.fluid_plans),
            supplements=self._ordered_records(records.supplements),
            dialysis_records=self._ordered_records(records.dialysis_records),
            oral_feeding_status_history=self._ordered_records(
                records.oral_feeding_status_history,
            ),
            food_preferences=self._ordered_records(records.food_preferences),
            misc_orders=self._ordered_records(records.misc_orders),
            nutrition_goals=self._ordered_records(records.nutrition_goals),
            edema=self._ordered_records(records.edema),
            meal_intakes=self._ordered_records(records.meal_intakes),
            appetite_observations=self._ordered_records(
                records.appetite_observations,
            ),
            gi_observations=self._ordered_records(records.gi_observations),
            wounds=self._ordered_records(records.wounds),
            clinical_facts=self._ordered_records(records.clinical_facts),
            progress_notes=self._ordered_records(records.progress_notes),
            assessments=self._ordered_records(person.assessments or ()),
            extracted_facts=self._ordered_records(person.extracted_facts or ()),
            conflicts=conflicts,
            derived_calculations=derived_calculations,
        )

    def _calculate_details(  # noqa: PLR0913
        self,
        *,
        person: Person,
        effective_date: date,
        age: int | None,
        current_weight: PersonWeight | None,
        weights: Sequence[PersonWeight],
        current_weight_goal: PersonNutritionGoal | None,
        current_dialysis: PersonDialysis | None,
        current_enteral_feeding: PersonEnteralFeeding | None,
        current_parenteral_nutrition: PersonParenteralNutrition | None,
        conflicts: Sequence[ClinicalConflict],
    ) -> DerivedPersonCalculations:
        """Run deterministic calculations supported by documented inputs."""
        anthropometrics = self._anthropometrics(person, current_weight, age)
        conflicting_concepts = {conflict.concept for conflict in conflicts}
        nutrition_needs = self._nutrition_needs(
            person=person,
            age=age,
            current_weight=current_weight,
            current_weight_goal=current_weight_goal,
            current_dialysis=current_dialysis,
            conflicting_concepts=conflicting_concepts,
        )
        return DerivedPersonCalculations(
            calculated_on=effective_date,
            anthropometrics=anthropometrics,
            weight_history=self._weight_changes(weights),
            nutrition_needs=nutrition_needs,
            tube_feed=self._tube_feed_calculation(current_enteral_feeding),
            parenteral_nutrition=self._parenteral_nutrition_calculation(
                current_parenteral_nutrition,
                anthropometrics.current_weight_kg,
            ),
        )

    @staticmethod
    def _anthropometrics(
        person: Person,
        current_weight: PersonWeight | None,
        age: int | None,
    ) -> AnthropometricCalculations:
        """Calculate all anthropometrics supported by documented inputs."""
        missing_inputs: list[str] = []
        weight_lb = current_weight.weight_lb if current_weight is not None else None
        height_in = person.height_in
        gender = PersonDetailBuilder._gender(person.sex)
        measured_at = (
            PersonDetailBuilder._measurement_datetime(current_weight)
            if current_weight is not None
            else None
        )
        if weight_lb is None:
            missing_inputs.append("dated_current_weight")
        if height_in is None:
            missing_inputs.append("height_in")
        if gender is None:
            missing_inputs.append("normalized_sex")
        if age is None:
            missing_inputs.append("age")

        weight_kg = Convert.to_kg(weight_lb) if weight_lb is not None else None
        bmi = (
            NutritionCalculator.calculate_bmi(weight_lb, height_in)
            if weight_lb is not None and height_in is not None
            else None
        )
        bmi_category = (
            NutritionCalculator.determine_bmi_category(bmi, age).value
            if bmi is not None and age is not None
            else None
        )
        ideal_weight = (
            NutritionCalculator.calculate_ibw(gender, height_in)
            if height_in is not None and gender is not None
            else None
        )
        adjusted_ideal_weight = (
            NutritionCalculator.calculate_aibw(weight_lb, height_in, gender)
            if weight_lb is not None and height_in is not None and gender is not None
            else None
        )
        mifflin = (
            NutritionCalculator.calculate_mifflin(
                weight_lb,
                height_in,
                gender,
                age,
            )
            if (
                weight_lb is not None
                and height_in is not None
                and gender is not None
                and age is not None
            )
            else None
        )
        return AnthropometricCalculations(
            current_weight_lb=weight_lb,
            current_weight_date=measured_at.date() if measured_at is not None else None,
            current_weight_kg=round(weight_kg, 2) if weight_kg is not None else None,
            bmi=bmi,
            bmi_category=bmi_category,
            ideal_weight_lb=(
                round(ideal_weight, 2) if ideal_weight is not None else None
            ),
            adjusted_ideal_weight_lb=(
                round(adjusted_ideal_weight, 2)
                if adjusted_ideal_weight is not None
                else None
            ),
            mifflin_kcal_day=mifflin,
            missing_inputs=missing_inputs,
        )

    @staticmethod
    def _nutrition_needs(  # noqa: PLR0913
        *,
        person: Person,
        age: int | None,
        current_weight: PersonWeight | None,
        current_weight_goal: PersonNutritionGoal | None,
        current_dialysis: PersonDialysis | None,
        conflicting_concepts: set[str],
    ) -> NutritionNeedsCalculation:
        """Calculate needs only when inputs and structured choices are unambiguous."""
        if "current_weight_goal" in conflicting_concepts:
            return NutritionNeedsCalculation(
                status="not_computed",
                reason="Multiple active weight-direction goals require review",
            )
        if "dialysis" in conflicting_concepts:
            return NutritionNeedsCalculation(
                status="not_computed",
                reason="Multiple equally current dialysis records require review",
            )

        gender = PersonDetailBuilder._gender(person.sex)
        missing_inputs: list[str] = []
        if current_weight is None:
            missing_inputs.append("dated_current_weight")
        if person.height_in is None:
            missing_inputs.append("height_in")
        if gender is None:
            missing_inputs.append("normalized_sex")
        if age is None:
            missing_inputs.append("age")
        if missing_inputs:
            return NutritionNeedsCalculation(
                status="not_computed",
                missing_inputs=missing_inputs,
            )
        narrowed_weight = typing.cast("PersonWeight", current_weight)
        narrowed_height = typing.cast("float", person.height_in)
        narrowed_gender = typing.cast("Gender", gender)
        narrowed_age = typing.cast("int", age)
        goal = PersonDetailBuilder._goal(current_weight_goal)
        dialysis = current_dialysis is not None
        data = EnergyNeedsInput(
            height_in=narrowed_height,
            weight_lb=narrowed_weight.weight_lb,
            gender=narrowed_gender,
            age=narrowed_age,
            goal=goal,
            dialysis=dialysis,
        )
        try:
            result = NutritionCalculator.calculate(data)
        except ValueError as error:
            return NutritionNeedsCalculation(
                status="not_computed",
                goal=goal.value,
                dialysis=dialysis,
                reason=str(error),
            )
        return NutritionNeedsCalculation(
            status="computed",
            result=result,
            goal=goal.value,
            dialysis=dialysis,
        )

    def _tube_feed_calculation(
        self,
        feeding: PersonEnteralFeeding | None,
    ) -> TubeFeedCalculation:
        """Calculate nutrition from an active documented tube-feed order."""
        if feeding is None:
            return TubeFeedCalculation(status="not_applicable")
        if self.tube_feed_calculator is None:
            return TubeFeedCalculation(
                status="not_computed",
                reason="A food repository is required to resolve the formula",
            )
        try:
            result = self.tube_feed_calculator.calculate_from_feeding(feeding)
        except ValueError as error:
            return TubeFeedCalculation(status="not_computed", reason=str(error))
        return TubeFeedCalculation(status="computed", result=result)

    def _parenteral_nutrition_calculation(
        self,
        prescription: PersonParenteralNutrition | None,
        weight_kg: float | None,
    ) -> ParenteralNutritionCalculation:
        """Calculate nutrition from an active documented PN prescription."""
        if prescription is None:
            return ParenteralNutritionCalculation(status="not_applicable")
        try:
            result = self.parenteral_nutrition_calculator.calculate_from_prescription(
                prescription,
                weight_kg=weight_kg,
            )
        except ValueError as error:
            return ParenteralNutritionCalculation(
                status="not_computed",
                reason=str(error),
            )
        return ParenteralNutritionCalculation(status="computed", result=result)

    @classmethod
    def _singleton(
        cls,
        concept: str,
        records: Sequence[_ClinicalRecordT],
        conflicts: list[ClinicalConflict],
    ) -> _ClinicalRecordT | None:
        """Return the newest active record unless clinical timestamps tie."""
        active = cls._active(records)
        if not active:
            return None
        newest_time = cls._clinical_time(active[0])
        tied = [item for item in active if cls._clinical_time(item) == newest_time]
        if len(tied) > 1:
            conflicts.append(
                ClinicalConflict(
                    concept=concept,
                    message=f"Multiple equally current active {concept} records",
                    record_ids=tuple(
                        record_id
                        for item in tied
                        if (record_id := cls._record_id(item)) is not None
                    ),
                ),
            )
            return None
        return active[0]

    @classmethod
    def _active(
        cls,
        records: Sequence[_ClinicalRecordT],
    ) -> list[_ClinicalRecordT]:
        """Return active records newest first by clinical timestamp."""
        return sorted(
            (
                record
                for record in records
                if getattr(
                    getattr(record, "status", None),
                    "value",
                    getattr(record, "status", None),
                )
                == ClinicalStatus.ACTIVE.value
            ),
            key=cls._clinical_sort_key,
            reverse=True,
        )

    @classmethod
    def _allergies(
        cls,
        records: Sequence[PersonAllergy],
    ) -> list[PersonAllergy]:
        """Keep allergies unless the source explicitly marks them inactive."""
        return sorted(
            (
                record
                for record in records
                if getattr(
                    getattr(record, "status", None),
                    "value",
                    getattr(record, "status", None),
                )
                != ClinicalStatus.INACTIVE.value
            ),
            key=cls._clinical_sort_key,
            reverse=True,
        )

    @classmethod
    def _active_medications(
        cls,
        records: Sequence[PersonMedication],
    ) -> list[PersonMedication]:
        """Keep active regimens without treating a shared drug name as conflict."""
        medications_by_regimen: dict[str, PersonMedication] = {}
        for medication in cls._active(records):
            medications_by_regimen.setdefault(medication.state_key, medication)
        return sorted(
            medications_by_regimen.values(),
            key=cls._clinical_sort_key,
            reverse=True,
        )

    @classmethod
    def _current_by_key(
        cls,
        concept: str,
        records: Sequence[_ClinicalRecordT],
        key: Callable[[_ClinicalRecordT], str],
        conflicts: list[ClinicalConflict],
    ) -> list[_ClinicalRecordT]:
        """Select the newest active record for each domain identity."""
        selected: list[_ClinicalRecordT] = []
        grouped: dict[str, list[_ClinicalRecordT]] = {}
        for record in cls._active(records):
            grouped.setdefault(key(record), []).append(record)
        for identity, matches in grouped.items():
            newest_time = cls._clinical_time(matches[0])
            tied = [item for item in matches if cls._clinical_time(item) == newest_time]
            if len(tied) > 1:
                conflicts.append(
                    ClinicalConflict(
                        concept=concept,
                        message=f"Conflicting active {concept} records for {identity}",
                        record_ids=tuple(
                            record_id
                            for item in tied
                            if (record_id := cls._record_id(item)) is not None
                        ),
                    ),
                )
                continue
            selected.append(matches[0])
        return sorted(selected, key=cls._clinical_sort_key, reverse=True)

    @staticmethod
    def _current_weight_goal(
        goals: Sequence[PersonNutritionGoal],
        conflicts: list[ClinicalConflict],
    ) -> PersonNutritionGoal | None:
        """Return one active directional weight goal or expose ambiguity."""
        weight_goal_types = {
            NutritionGoalType.WEIGHT_GAIN,
            NutritionGoalType.WEIGHT_MAINTENANCE,
            NutritionGoalType.WEIGHT_LOSS,
        }
        weight_goals = [goal for goal in goals if goal.goal_type in weight_goal_types]
        if len(weight_goals) > 1:
            conflicts.append(
                ClinicalConflict(
                    concept="current_weight_goal",
                    message="Multiple active weight-direction nutrition goals",
                    record_ids=tuple(
                        goal.id for goal in weight_goals if goal.id is not None
                    ),
                ),
            )
            return None
        return weight_goals[0] if weight_goals else None

    @classmethod
    def _ordered_weights(
        cls,
        weights: Sequence[PersonWeight],
    ) -> list[PersonWeight]:
        """Order weights newest first using measurement time and record ID."""
        return sorted(
            weights,
            key=lambda weight: (
                cls._measurement_datetime(weight) or datetime.min.replace(tzinfo=UTC),
                weight.id or -1,
            ),
            reverse=True,
        )

    @classmethod
    def _ordered_records(cls, records: Sequence[_RecordT]) -> list[_RecordT]:
        """Order any bounded record collection by clinical time and ID."""
        return sorted(records, key=cls._generic_sort_key, reverse=True)

    @classmethod
    def _clinical_sort_key(
        cls,
        record: object,
    ) -> tuple[bool, datetime, int]:
        value = cls._clinical_time(record)
        return (
            value is not None,
            value or datetime.min.replace(tzinfo=UTC),
            cls._record_id(record) or -1,
        )

    @classmethod
    def _generic_sort_key(cls, record: object) -> tuple[bool, datetime, int]:
        value = cls._record_time(record)
        record_id = getattr(record, "id", None)
        return (
            value is not None,
            value or datetime.min.replace(tzinfo=UTC),
            record_id if isinstance(record_id, int) else -1,
        )

    @staticmethod
    def _record_id(record: object) -> int | None:
        record_id = getattr(record, "id", None)
        return record_id if isinstance(record_id, int) else None

    @staticmethod
    def _clinical_time(record: object) -> datetime | None:
        """Return clinical state time without using insertion time as evidence."""
        values = [
            parsed
            for parsed in (
                PersonDetailBuilder._as_datetime(
                    getattr(record, field_name, None),
                )
                for field_name in ("effective_at", "observed_at")
            )
            if parsed is not None
        ]
        return max(values) if values else None

    @staticmethod
    def _record_time(record: object) -> datetime | None:
        """Return the best available timestamp for history presentation order."""
        clinical_values = [
            parsed
            for parsed in (
                PersonDetailBuilder._as_datetime(
                    getattr(record, field_name, None),
                )
                for field_name in (
                    "effective_at",
                    "observed_at",
                    "measured_at",
                    "note_date",
                    "assessment_date",
                    "extracted_at",
                )
            )
            if parsed is not None
        ]
        if clinical_values:
            return max(clinical_values)
        return PersonDetailBuilder._as_datetime(getattr(record, "created_at", None))

    @classmethod
    def _weight_changes(
        cls,
        weights: Sequence[PersonWeight],
    ) -> list[WeightChangeDetail]:
        """Compare all dated prior weights with the latest valid weight."""
        dated_weights = [
            weight
            for weight in cls._ordered_weights(weights)
            if cls._measurement_datetime(weight) is not None and weight.weight_lb > 0
        ]
        if not dated_weights:
            return []
        current = dated_weights[0]
        current_date = cls._measurement_datetime(current)
        if current_date is None:
            return []
        changes: list[WeightChangeDetail] = []
        for prior in dated_weights[1:]:
            prior_date = cls._measurement_datetime(prior)
            if prior_date is None:
                continue
            elapsed_days = (current_date.date() - prior_date.date()).days
            if elapsed_days <= 0:
                continue
            delta = current.weight_lb - prior.weight_lb
            percent_change = delta / prior.weight_lb * 100
            interval, threshold = WeightHistoryCalculator.significance_interval(
                current,
                prior,
            )
            direction = "loss" if delta < 0 else "gain" if delta > 0 else "stable"
            rounded_change = round(delta, 2)
            absolute_change = round(abs(delta), 2)
            absolute_percent_change = round(abs(percent_change), 2)
            changes.append(
                WeightChangeDetail(
                    current_measured_at=current_date,
                    latest_weight_lb=current.weight_lb,
                    prior_measured_at=prior_date,
                    prior_weight_lb=prior.weight_lb,
                    change_lb=rounded_change,
                    absolute_change_lb=absolute_change,
                    percent_change=absolute_percent_change,
                    direction=direction,
                    elapsed_days=elapsed_days,
                    elapsed_timeframe=WeightHistoryCalculator.format_elapsed_months(
                        current_date.date(),
                        prior_date.date(),
                    ),
                    significance_interval=interval,
                    significance_threshold_percent=threshold,
                    clinically_significant=(
                        WeightHistoryCalculator.is_signficant_change(current, prior)
                        if interval is not None
                        else False
                    ),
                    comparison_text=cls._format_weight_comparison(
                        current_date=current_date,
                        prior_date=prior_date,
                        prior_weight_lb=prior.weight_lb,
                        absolute_change_lb=absolute_change,
                        percent_change=absolute_percent_change,
                        direction=direction,
                    ),
                ),
            )
        return changes

    @classmethod
    def _format_weight_comparison(  # noqa: PLR0913
        cls,
        *,
        current_date: datetime,
        prior_date: datetime,
        prior_weight_lb: float,
        absolute_change_lb: float,
        percent_change: float,
        direction: typing.Literal["loss", "gain", "stable"],
    ) -> str:
        """Format one prior weight's deterministic change to the latest weight."""
        elapsed_timeframe = WeightHistoryCalculator.format_elapsed_months(
            current_date.date(),
            prior_date.date(),
        )
        return (
            f"{prior_date:%m/%d/%y}: {cls._format_number(prior_weight_lb)} lbs; "
            f"{cls._format_number(absolute_change_lb)} lbs {direction} "
            f"({cls._format_number(percent_change)}%) over "
            f"{elapsed_timeframe} compared with latest weight"
        )

    @staticmethod
    def _format_number(value: float) -> str:
        """Format a calculated weight value without unnecessary trailing zeros."""
        return f"{value:.2f}".rstrip("0").rstrip(".")

    @staticmethod
    def _gender(value: str | None) -> Gender | None:
        normalized = " ".join((value or "").casefold().split())
        if normalized in {"f", "female"}:
            return Gender.FEMALE
        if normalized in {"m", "male"}:
            return Gender.MALE
        return None

    @staticmethod
    def _goal(goal: PersonNutritionGoal | None) -> Goal:
        if goal is None:
            return Goal.MAINTAIN
        return {
            NutritionGoalType.WEIGHT_LOSS: Goal.LOSE,
            NutritionGoalType.WEIGHT_MAINTENANCE: Goal.MAINTAIN,
            NutritionGoalType.WEIGHT_GAIN: Goal.GAIN,
        }.get(goal.goal_type, Goal.MAINTAIN)

    @staticmethod
    def _calculate_age(date_of_birth: date | None, on_date: date) -> int | None:
        if date_of_birth is None:
            return None
        return (
            on_date.year
            - date_of_birth.year
            - ((on_date.month, on_date.day) < (date_of_birth.month, date_of_birth.day))
        )

    @staticmethod
    def _measurement_datetime(weight: PersonWeight) -> datetime | None:
        return PersonDetailBuilder._as_datetime(weight.measured_at)

    @staticmethod
    def _as_datetime(value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return datetime.combine(value, datetime.min.time(), tzinfo=UTC)
        try:
            parsed = _DATETIME_ADAPTER.validate_python(value)
        except ValidationError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    @staticmethod
    def _as_date(value: object) -> date | None:
        if value is None:
            return None
        try:
            return _DATE_ADAPTER.validate_python(value)
        except ValidationError:
            return None


__all__ = ["PersonDetailBuilder"]
