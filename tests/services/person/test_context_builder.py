"""Tests for deterministic person current-state assembly."""

# ruff: noqa: PLR2004

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from ntk.models.sql.clinical import (
    AppetiteLevel,
    ClinicalStatus,
    DialysisType,
    GISymptom,
    LipidDeliveryType,
    NutritionGoalType,
    ParenteralNutritionStatus,
    PersonAppetiteObservation,
    PersonDialysis,
    PersonDiet,
    PersonFluidPlan,
    PersonGIObservation,
    PersonMedication,
    PersonNutritionGoal,
    PersonOralFeedingStatus,
    PersonParenteralNutrition,
    PersonWeight,
)
from ntk.models.sql.person import Person
from ntk.pipelines.assessment.create.context_budgeter import ContextBudgeter
from ntk.repositories.person_repo import PersonAssessmentRecords
from ntk.services.person.detail_builder import PersonDetailBuilder

_OLDER = datetime(2026, 3, 1, tzinfo=UTC)
_NEWER = datetime(2026, 9, 1, tzinfo=UTC)


def _diet(
    name: str,
    observed_at: datetime,
    *,
    record_id: int,
    created_at: datetime,
) -> PersonDiet:
    return PersonDiet(
        id=record_id,
        person_id=1,
        diet_type=name,
        status=ClinicalStatus.ACTIVE,
        observed_at=observed_at,
        created_at=created_at,
        state_key=name.casefold(),
        extracted_fact_id=record_id,
    )


def test_older_clinical_state_imported_later_does_not_become_current() -> None:
    newer = _diet(
        "Renal",
        _NEWER,
        record_id=1,
        created_at=_NEWER,
    )
    historical_import = _diet(
        "Regular",
        _OLDER,
        record_id=2,
        created_at=_NEWER + timedelta(days=1),
    )

    context = PersonDetailBuilder().build(
        Person(id=1, name="Person"),
        PersonAssessmentRecords(diets=[historical_import, newer]),
    )

    assert context.current_diet is newer


def test_equally_current_singletons_are_reported_as_a_conflict() -> None:
    context = PersonDetailBuilder().build(
        Person(id=1, name="Person"),
        PersonAssessmentRecords(
            diets=[
                _diet("Renal", _NEWER, record_id=1, created_at=_NEWER),
                _diet("Cardiac", _NEWER, record_id=2, created_at=_NEWER),
            ],
        ),
    )

    assert context.current_diet is None
    assert context.conflicts[0].concept == "diet"
    assert context.conflicts[0].record_ids == (2, 1)


def test_active_medications_keep_distinct_active_regimens() -> None:
    records = PersonAssessmentRecords(
        medications=[
            PersonMedication(
                id=1,
                person_id=1,
                name="Lasix",
                dose=20,
                dose_unit="mg",
                status=ClinicalStatus.ACTIVE,
                observed_at=_OLDER,
                created_at=_NEWER + timedelta(days=1),
                state_key="lasix-20",
                extracted_fact_id=1,
            ),
            PersonMedication(
                id=2,
                person_id=1,
                name="Lasix",
                dose=40,
                dose_unit="mg",
                status=ClinicalStatus.ACTIVE,
                observed_at=_NEWER,
                created_at=_NEWER,
                state_key="lasix-40",
                extracted_fact_id=2,
            ),
        ],
    )

    context = PersonDetailBuilder().build(
        Person(id=1, name="Person"),
        records,
    )

    assert [medication.dose for medication in context.active_medications] == [40, 20]


def test_structured_dialysis_and_nutrition_goal_drive_needs_profile() -> None:
    person = Person(
        id=1,
        name="Doe, Jane",
        date_of_birth=date(1940, 1, 1),
        sex="female",
        height_in=64,
    )
    records = PersonAssessmentRecords(
        weights=[
            PersonWeight(
                id=1,
                person_id=1,
                weight_lb=140,
                measured_at=_NEWER,
            ),
        ],
        dialysis_records=[
            PersonDialysis(
                id=1,
                person_id=1,
                dialysis_type=DialysisType.HEMODIALYSIS,
                schedule="M/W/F",
                status=ClinicalStatus.ACTIVE,
                observed_at=_NEWER,
                state_key="hd-mwf",
                extracted_fact_id=1,
            ),
        ],
        nutrition_goals=[
            PersonNutritionGoal(
                id=2,
                person_id=1,
                goal_type=NutritionGoalType.WEIGHT_GAIN,
                status=ClinicalStatus.ACTIVE,
                observed_at=_NEWER,
                state_key="gain",
                extracted_fact_id=2,
            ),
        ],
    )

    context = PersonDetailBuilder().build(person, records)
    needs = context.derived_calculations.nutrition_needs

    assert needs.status == "computed"
    assert needs.result is not None
    assert needs.dialysis is True
    assert needs.goal == "gain"


def test_budgeter_keeps_current_state_and_bounds_history() -> None:
    diets = [
        _diet(
            f"Diet {index}",
            _NEWER - timedelta(days=index),
            record_id=index + 1,
            created_at=_NEWER,
        )
        for index in range(10)
    ]
    weights = [
        PersonWeight(
            id=index + 1,
            person_id=1,
            weight_lb=150 + index,
            measured_at=_NEWER - timedelta(days=index),
        )
        for index in range(20)
    ]
    context = PersonDetailBuilder().build(
        Person(id=1, name="Person"),
        PersonAssessmentRecords(diets=diets, weights=weights),
    )

    budgeted = ContextBudgeter().budget(context)

    person = budgeted.assessment_context.person
    assert person.current_diet is not None
    assert person.current_diet.diet_type == "Diet 0"
    assert len(person.weight_history) == 12
    assert budgeted.omitted_record_counts == {"weight_history": 8}


def test_context_keeps_new_domains_separate_and_calculates_pn() -> None:
    person = Person(
        id=1,
        name="Doe, Jane",
        date_of_birth=date(1940, 1, 1),
        sex="female",
        height_in=64,
    )
    records = PersonAssessmentRecords(
        weights=[
            PersonWeight(
                id=1,
                person_id=1,
                weight_lb=132.277,
                measured_at=_NEWER,
            ),
        ],
        parenteral_nutrition_records=[
            PersonParenteralNutrition(
                id=2,
                person_id=1,
                total_volume_ml=1800,
                hours_per_day=12,
                dextrose_g_per_l=200,
                amino_acid_g_per_l=50,
                lipid_delivery=LipidDeliveryType.NONE,
                status=ParenteralNutritionStatus.ACTIVE,
                observed_at=_NEWER,
                state_key="pn",
                extracted_fact_id=2,
            ),
        ],
        fluid_plans=[
            PersonFluidPlan(
                id=3,
                person_id=1,
                restriction_ml_day=1500,
                status=ClinicalStatus.ACTIVE,
                observed_at=_NEWER,
                state_key="fluid",
                extracted_fact_id=3,
            ),
        ],
        appetite_observations=[
            PersonAppetiteObservation(
                id=4,
                person_id=1,
                appetite=AppetiteLevel.POOR,
                observed_at=_NEWER,
                observation_key="appetite-new",
                extracted_fact_id=4,
            ),
            PersonAppetiteObservation(
                id=5,
                person_id=1,
                appetite=AppetiteLevel.GOOD,
                observed_at=_OLDER,
                observation_key="appetite-old",
                extracted_fact_id=5,
            ),
        ],
        gi_observations=[
            PersonGIObservation(
                id=6,
                person_id=1,
                symptom=GISymptom.NAUSEA,
                observed_at=_NEWER,
                observation_key="gi",
                extracted_fact_id=6,
            ),
        ],
        oral_feeding_status_history=[
            PersonOralFeedingStatus(
                id=7,
                person_id=1,
                swallowing_difficulty=True,
                status=ClinicalStatus.ACTIVE,
                observed_at=_NEWER,
                state_key="oral",
                extracted_fact_id=7,
            ),
        ],
    )

    detail = PersonDetailBuilder().build(person, records)
    calculation = detail.derived_calculations.parenteral_nutrition

    assert detail.current_fluid_plan is not None
    assert detail.current_fluid_plan.restriction_ml_day == 1500
    assert detail.current_oral_feeding_status is not None
    assert detail.current_oral_feeding_status.swallowing_difficulty is True
    assert detail.appetite_observations[0].appetite is AppetiteLevel.POOR
    assert detail.gi_observations[0].symptom is GISymptom.NAUSEA
    assert calculation.status == "computed"
    assert calculation.result is not None
    assert calculation.result.total_kcal_day == 1584
    assert calculation.result.gir_mg_kg_min == 8.32


def test_multiple_active_weight_directions_are_an_explicit_conflict() -> None:
    goals = [
        PersonNutritionGoal(
            id=index,
            person_id=1,
            goal_type=goal_type,
            status=ClinicalStatus.ACTIVE,
            observed_at=_NEWER,
            state_key=goal_type.value,
            extracted_fact_id=index,
        )
        for index, goal_type in enumerate(
            (
                NutritionGoalType.WEIGHT_GAIN,
                NutritionGoalType.WEIGHT_MAINTENANCE,
            ),
            start=1,
        )
    ]

    context = PersonDetailBuilder().build(
        Person(id=1, name="Person"),
        PersonAssessmentRecords(nutrition_goals=goals),
    )

    assert context.current_weight_goal is None
    assert any(item.concept == "current_weight_goal" for item in context.conflicts)
