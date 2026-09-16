"""Tests for deterministic person-detail construction."""

from __future__ import annotations

from datetime import UTC, date, datetime

from engine.models.sql.clinical import ClinicalStatus, PersonMedication, PersonWeight
from engine.models.sql.facility import Facility
from engine.models.sql.person import Person
from engine.repositories.person_repo import PersonClinicalRecords
from engine.services.person.detail_builder import PersonDetailBuilder

_EXPECTED_WEIGHT_KG = 70


def test_weight_history_exposes_each_prior_weight_compared_to_latest() -> None:
    latest_date = datetime(2026, 8, 4, tzinfo=UTC)
    one_month_date = datetime(2026, 7, 4, tzinfo=UTC)
    three_month_date = datetime(2026, 5, 4, tzinfo=UTC)
    detail = PersonDetailBuilder().build(
        Person(id=1, name="Doe, Jane", first_name="Jane", last_name="Doe"),
        PersonClinicalRecords(
            weights=[
                PersonWeight(
                    person_id=1,
                    measured_at=three_month_date,
                    weight_lb=171.6,
                ),
                PersonWeight(
                    person_id=1,
                    measured_at=latest_date,
                    weight_lb=176.8,
                ),
                PersonWeight(
                    person_id=1,
                    measured_at=one_month_date,
                    weight_lb=174.0,
                ),
            ],
        ),
    )

    assert detail.current_weight is not None
    assert detail.current_weight.weight_lb == 176.8  # noqa: PLR2004
    comparisons = detail.derived_calculations.weight_history
    assert [comparison.current_measured_at for comparison in comparisons] == [
        latest_date,
        latest_date,
    ]
    assert [comparison.latest_weight_lb for comparison in comparisons] == [
        176.8,
        176.8,
    ]
    assert [comparison.prior_measured_at for comparison in comparisons] == [
        one_month_date,
        three_month_date,
    ]
    assert [comparison.prior_weight_lb for comparison in comparisons] == [
        174.0,
        171.6,
    ]
    assert [comparison.percent_change for comparison in comparisons] == [1.61, 3.03]
    assert [comparison.absolute_change_lb for comparison in comparisons] == [2.8, 5.2]
    assert [comparison.direction for comparison in comparisons] == ["gain", "gain"]
    assert [comparison.significance_interval for comparison in comparisons] == [
        "1 month",
        "3 months",
    ]
    assert [comparison.elapsed_timeframe for comparison in comparisons] == [
        "1 month",
        "3 months",
    ]
    assert [comparison.comparison_text for comparison in comparisons] == [
        (
            "07/04/26: 174 lbs; 2.8 lbs gain (1.61%) over 1 month compared with "
            "latest weight"
        ),
        (
            "05/04/26: 171.6 lbs; 5.2 lbs gain (3.03%) over 3 months compared "
            "with latest weight"
        ),
    ]
    assert all("month" in comparison.comparison_text for comparison in comparisons)


def test_same_medication_name_with_distinct_active_regimens_is_not_a_conflict() -> None:
    observed_at = datetime(2026, 9, 9, tzinfo=UTC)
    detail = PersonDetailBuilder().build(
        Person(id=1, name="Doe, Jane", first_name="Jane", last_name="Doe"),
        PersonClinicalRecords(
            medications=[
                PersonMedication(
                    id=1,
                    person_id=1,
                    name="Acetaminophen",
                    dose=650,
                    dose_text="650",
                    dose_unit="mg",
                    route="PO",
                    frequency="Q6H PRN",
                    status=ClinicalStatus.ACTIVE,
                    observed_at=observed_at,
                    state_key="acetaminophen-650-prn",
                    extracted_fact_id=1,
                ),
                PersonMedication(
                    id=2,
                    person_id=1,
                    name="Acetaminophen",
                    dose=325,
                    dose_text="325",
                    dose_unit="mg",
                    route="PO",
                    frequency="BID",
                    status=ClinicalStatus.ACTIVE,
                    observed_at=observed_at,
                    state_key="acetaminophen-325-bid",
                    extracted_fact_id=2,
                ),
            ],
        ),
    )

    assert {medication.state_key for medication in detail.active_medications} == {
        "acetaminophen-650-prn",
        "acetaminophen-325-bid",
    }
    assert not any(conflict.concept == "medication" for conflict in detail.conflicts)


def test_repeated_medication_regimen_keeps_the_newest_record() -> None:
    older = datetime(2026, 9, 8, tzinfo=UTC)
    newer = datetime(2026, 9, 9, tzinfo=UTC)
    detail = PersonDetailBuilder().build(
        Person(id=1, name="Doe, Jane", first_name="Jane", last_name="Doe"),
        PersonClinicalRecords(
            medications=[
                PersonMedication(
                    id=1,
                    person_id=1,
                    name="Acetaminophen",
                    status=ClinicalStatus.ACTIVE,
                    observed_at=older,
                    state_key="acetaminophen-regimen",
                    extracted_fact_id=1,
                ),
                PersonMedication(
                    id=2,
                    person_id=1,
                    name="Acetaminophen",
                    status=ClinicalStatus.ACTIVE,
                    observed_at=newer,
                    state_key="acetaminophen-regimen",
                    extracted_fact_id=2,
                ),
            ],
        ),
    )

    assert [medication.id for medication in detail.active_medications] == [2]
    assert not any(conflict.concept == "medication" for conflict in detail.conflicts)


def test_person_detail_includes_direct_facility_identity() -> None:
    facility = Facility(id=2, facility_identifier="FAC", name="Facility")
    person = Person(
        id=1,
        name="Person",
        facility_id=2,
        facility=facility,
        person_identifier="R-1",
    )

    detail = PersonDetailBuilder().build(person, PersonClinicalRecords())

    assert detail.facility_id == 2  # noqa: PLR2004
    assert detail.person_identifier == "R-1"
    assert detail.facility is facility


def test_person_detail_contains_demographics_and_derived_age() -> None:
    birth_date = date(1946, 2, 1)
    person = Person(
        id=1,
        name="Person",
        date_of_birth=birth_date,
        sex="f",
        height_in=64.5,
    )

    detail = PersonDetailBuilder().build(
        person,
        PersonClinicalRecords(),
        on_date=date(2026, 9, 4),
    )

    assert detail.date_of_birth == birth_date
    assert detail.sex == "f"
    assert detail.height_in == 64.5  # noqa: PLR2004
    assert detail.age == 80  # noqa: PLR2004


def test_person_age_is_derived_from_date_of_birth() -> None:
    expected_before_birthday = 79
    expected_on_birthday = 80
    assert (
        PersonDetailBuilder._calculate_age(  # noqa: SLF001
            date(1946, 9, 1),
            date(2026, 8, 30),
        )
        == expected_before_birthday
    )
    assert (
        PersonDetailBuilder._calculate_age(  # noqa: SLF001
            date(1946, 8, 30),
            date(2026, 8, 30),
        )
        == expected_on_birthday
    )


def test_person_detail_exposes_deterministic_calculations() -> None:
    person = Person(
        id=1,
        name="Person",
        date_of_birth=date(1946, 9, 4),
        sex="female",
        height_in=64,
    )
    records = PersonClinicalRecords(
        weights=[
            PersonWeight(
                person_id=1,
                measured_at=datetime(2026, 6, 3, tzinfo=UTC),
                weight_lb=180,
            ),
            PersonWeight(
                person_id=1,
                measured_at=datetime(2026, 9, 1, tzinfo=UTC),
                weight_lb=154,
            ),
            PersonWeight(
                person_id=1,
                measured_at=datetime(2026, 8, 2, tzinfo=UTC),
                weight_lb=170,
            ),
        ],
    )

    detail = PersonDetailBuilder().build(
        person,
        records,
        on_date=date(2026, 9, 4),
    )
    calculations = detail.derived_calculations

    assert detail.age == 80  # noqa: PLR2004
    assert calculations.anthropometrics.current_weight_kg == _EXPECTED_WEIGHT_KG
    assert calculations.anthropometrics.current_weight_date == date(2026, 9, 1)
    assert [change.elapsed_days for change in calculations.weight_history] == [30, 90]
    assert all(change.direction == "loss" for change in calculations.weight_history)
    assert calculations.nutrition_needs.status == "computed"
    assert calculations.nutrition_needs.result is not None


def test_person_detail_orders_weights_and_reports_missing_needs_inputs() -> None:
    person = Person(id=1, name="Person", sex="unknown", height_in=64)
    records = PersonClinicalRecords(
        weights=[
            PersonWeight(
                person_id=1,
                measured_at=datetime(2026, 8, 1, tzinfo=UTC),
                weight_lb=150,
            ),
            PersonWeight(
                person_id=1,
                measured_at=datetime(2026, 9, 1, tzinfo=UTC),
                weight_lb=145,
            ),
        ],
    )

    detail = PersonDetailBuilder().build(person, records)

    assert [weight.weight_lb for weight in detail.weights] == [145, 150]
    assert detail.derived_calculations.anthropometrics.bmi is not None
    assert detail.derived_calculations.nutrition_needs.status == "not_computed"
    assert detail.derived_calculations.nutrition_needs.missing_inputs == [
        "normalized_sex",
        "age",
    ]
