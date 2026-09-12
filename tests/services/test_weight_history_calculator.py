"""Tests for person weight-history calculations and formatting."""

from __future__ import annotations

import typing
from datetime import UTC, datetime, timedelta

import pytest

from ntk.models.sql.clinical.weight import PersonWeight
from ntk.services.calculators.weight_history_calculator import WeightHistoryCalculator

_LATEST_DATE = datetime(2026, 9, 2, tzinfo=UTC)


def _weight(weight_lb: float, days_ago: int, *, identifier: int) -> PersonWeight:
    return PersonWeight(
        id=identifier,
        person_id=1,
        weight_lb=weight_lb,
        measured_at=_LATEST_DATE - timedelta(days=days_ago),
    )


@pytest.mark.parametrize(
    ("method", "significant_weight", "non_significant_weight"),
    [
        (WeightHistoryCalculator.is_significant_change_one_month, 95.0, 95.01),
        (WeightHistoryCalculator.is_significant_change_three_months, 92.5, 92.51),
        (WeightHistoryCalculator.is_significant_change_six_months, 90.0, 90.01),
    ],
)
def test_period_methods_use_inclusive_absolute_thresholds(
    method: typing.Callable[[float, float], bool],
    significant_weight: float,
    non_significant_weight: float,
) -> None:
    assert method(significant_weight, 100) is True
    assert method(non_significant_weight, 100) is False
    assert method(200 - significant_weight, 100) is True


@pytest.mark.parametrize(
    ("days_ago", "previous_weight", "expected"),
    [
        (30, 106, True),
        (31, 106, True),
        (90, 108, False),
        (90, 110, True),
        (91, 110, True),
        (180, 112, True),
        (181, 200, True),
        (185, 200, False),
    ],
)
def test_combined_method_uses_threshold_for_elapsed_time(
    days_ago: int,
    previous_weight: float,
    expected: bool,  # noqa: FBT001
) -> None:
    assert (
        WeightHistoryCalculator.is_signficant_change(
            _weight(100, 0, identifier=1),
            _weight(previous_weight, days_ago, identifier=2),
        )
        is expected
    )


def test_format_weights_lists_latest_then_changes_from_latest() -> None:
    formatted = WeightHistoryCalculator.format_weights(
        [
            _weight(100, 30, identifier=2),
            _weight(90, 0, identifier=1),
            _weight(80, 90, identifier=3),
        ],
    )

    assert formatted.splitlines() == [
        "Latest weight: 2026-09-02: 90 lbs",
        ("2026-08-03: 100 lbs; 10% weight loss, 10 lbs over 1 month to latest weight"),
        (
            "2026-06-04: 80 lbs; 12.5% weight gain, 10 lbs over 3 months "
            "to latest weight"
        ),
    ]


def test_tool_payload_timestamp_strings_are_normalized() -> None:
    latest = PersonWeight(
        person_id=1,
        weight_lb=90,
        measured_at="2026-09-02T00:00:00Z",
    )
    previous = PersonWeight(
        person_id=1,
        weight_lb=100,
        measured_at="2026-08-03T00:00:00Z",
    )

    assert WeightHistoryCalculator.is_signficant_change(latest, previous) is True
    assert WeightHistoryCalculator.format_weights([previous, latest]).splitlines() == [
        "Latest weight: 2026-09-02: 90 lbs",
        ("2026-08-03: 100 lbs; 10% weight loss, 10 lbs over 1 month to latest weight"),
    ]


def test_elapsed_timeframe_uses_calendar_months() -> None:
    assert (
        WeightHistoryCalculator.format_elapsed_months(
            datetime(2026, 9, 1, tzinfo=UTC).date(),
            datetime(2026, 7, 28, tzinfo=UTC).date(),
        )
        == "1 month"
    )


def test_elapsed_timeframe_rounds_months_without_decimals() -> None:
    assert (
        WeightHistoryCalculator.format_elapsed_months(
            datetime(2026, 9, 1, tzinfo=UTC).date(),
            datetime(2026, 7, 16, tzinfo=UTC).date(),
        )
        == "2 months"
    )
    assert (
        WeightHistoryCalculator.format_elapsed_months(
            datetime(2026, 9, 1, tzinfo=UTC).date(),
            datetime(2026, 8, 25, tzinfo=UTC).date(),
        )
        == "<1 month"
    )


def test_invalid_weights_raise_clear_errors() -> None:
    with pytest.raises(ValueError, match="measurement date"):
        WeightHistoryCalculator.format_weights(
            [
                PersonWeight(
                    person_id=1,
                    measured_at=typing.cast("datetime", None),
                    weight_lb=100,
                ),
            ],
        )

    with pytest.raises(ValueError, match="greater than zero"):
        WeightHistoryCalculator.is_significant_change_one_month(100, 0)
