"""Tests for deterministic person-detail construction."""

from __future__ import annotations

from datetime import UTC, datetime

from ntk.models.sql.clinical import ClinicalStatus, PersonMedication, PersonWeight
from ntk.models.sql.person import Person
from ntk.repositories.person_repo import PersonAssessmentRecords
from ntk.services.person.detail_builder import PersonDetailBuilder


def test_weight_history_exposes_each_prior_weight_compared_to_latest() -> None:
    latest_date = datetime(2026, 8, 4, tzinfo=UTC)
    one_month_date = datetime(2026, 7, 4, tzinfo=UTC)
    three_month_date = datetime(2026, 5, 4, tzinfo=UTC)
    detail = PersonDetailBuilder().build(
        Person(id=1, name="Doe, Jane", first_name="Jane", last_name="Doe"),
        PersonAssessmentRecords(
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
        PersonAssessmentRecords(
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
        PersonAssessmentRecords(
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
