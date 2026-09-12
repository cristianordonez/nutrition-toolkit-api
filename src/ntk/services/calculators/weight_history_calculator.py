"""Calculate and format clinically relevant person weight changes."""

from __future__ import annotations

import calendar
import math
import typing
from datetime import date, datetime

from pydantic import TypeAdapter, ValidationError

from ntk.models.sql.clinical.weight import PersonWeight  # noqa: TC001

_ONE_MONTH_THRESHOLD_PERCENT = 5.0
_THREE_MONTH_THRESHOLD_PERCENT = 7.5
_SIX_MONTH_THRESHOLD_PERCENT = 10.0
_DATETIME_ADAPTER = TypeAdapter(datetime)


class WeightHistoryCalculator:
    """Provide stateless weight-history methods suitable for agent tools."""

    @staticmethod
    def is_significant_change_one_month(
        latest_weight_lb: float,
        previous_weight_lb: float,
    ) -> bool:
        """Return whether the absolute weight change is at least 5%."""
        return (
            WeightHistoryCalculator._absolute_percent_change(
                latest_weight_lb,
                previous_weight_lb,
            )
            >= _ONE_MONTH_THRESHOLD_PERCENT
        )

    @staticmethod
    def is_significant_change_three_months(
        latest_weight_lb: float,
        previous_weight_lb: float,
    ) -> bool:
        """Return whether the absolute weight change is at least 7.5%."""
        return (
            WeightHistoryCalculator._absolute_percent_change(
                latest_weight_lb,
                previous_weight_lb,
            )
            >= _THREE_MONTH_THRESHOLD_PERCENT
        )

    @staticmethod
    def is_significant_change_six_months(
        latest_weight_lb: float,
        previous_weight_lb: float,
    ) -> bool:
        """Return whether the absolute weight change is at least 10%."""
        return (
            WeightHistoryCalculator._absolute_percent_change(
                latest_weight_lb,
                previous_weight_lb,
            )
            >= _SIX_MONTH_THRESHOLD_PERCENT
        )

    @staticmethod
    def is_signficant_change(
        latest_weight: PersonWeight,
        previous_weight: PersonWeight,
    ) -> bool:
        """Apply the threshold matching the time between two dated weights."""
        interval, _threshold = WeightHistoryCalculator.significance_interval(
            latest_weight,
            previous_weight,
        )
        if interval is None:
            return False
        if interval == "1 month":
            return WeightHistoryCalculator.is_significant_change_one_month(
                latest_weight.weight_lb,
                previous_weight.weight_lb,
            )
        if interval == "3 months":
            return WeightHistoryCalculator.is_significant_change_three_months(
                latest_weight.weight_lb,
                previous_weight.weight_lb,
            )
        return WeightHistoryCalculator.is_significant_change_six_months(
            latest_weight.weight_lb,
            previous_weight.weight_lb,
        )

    @staticmethod
    def significance_interval(
        latest_weight: PersonWeight,
        previous_weight: PersonWeight,
    ) -> tuple[
        typing.Literal["1 month", "3 months", "6 months"] | None,
        float | None,
    ]:
        """Return the clinical threshold window using calendar-month boundaries."""
        latest_date = WeightHistoryCalculator._measurement_date(latest_weight).date()
        previous_date = WeightHistoryCalculator._measurement_date(
            previous_weight,
        ).date()
        if previous_date >= latest_date:
            return None, None
        if latest_date <= WeightHistoryCalculator._add_months(previous_date, 1):
            return "1 month", _ONE_MONTH_THRESHOLD_PERCENT
        if latest_date <= WeightHistoryCalculator._add_months(previous_date, 3):
            return "3 months", _THREE_MONTH_THRESHOLD_PERCENT
        if latest_date <= WeightHistoryCalculator._add_months(previous_date, 6):
            return "6 months", _SIX_MONTH_THRESHOLD_PERCENT
        return None, None

    @staticmethod
    def _add_months(value: date, months: int) -> date:
        """Add calendar months while clamping to the destination month's last day."""
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, calendar.monthrange(year, month)[1])
        return value.replace(year=year, month=month, day=day)

    @staticmethod
    def format_weights(weights: list[PersonWeight]) -> str:
        """Format dated weights newest-first with changes from the latest value."""
        dated_weights = WeightHistoryCalculator._validated_dated_weights(weights)
        ordered_weights = sorted(
            dated_weights,
            key=WeightHistoryCalculator._sort_key,
            reverse=True,
        )
        latest = ordered_weights[0]
        latest_date = WeightHistoryCalculator._measurement_date(latest)
        lines = [
            (
                f"Latest weight: {latest_date.date().isoformat()}: "
                f"{WeightHistoryCalculator._format_number(latest.weight_lb)} lbs"
            ),
        ]
        for weight in ordered_weights[1:]:
            measured_at = WeightHistoryCalculator._measurement_date(weight)
            elapsed_timeframe = WeightHistoryCalculator.format_elapsed_months(
                latest_date.date(),
                measured_at.date(),
            )
            change_lb = latest.weight_lb - weight.weight_lb
            percent_change = (change_lb / weight.weight_lb) * 100
            if change_lb < 0:
                direction = "loss"
            elif change_lb > 0:
                direction = "gain"
            else:
                direction = "change"
            lines.append(
                f"{measured_at.date().isoformat()}: "
                f"{WeightHistoryCalculator._format_number(weight.weight_lb)} lbs; "
                f"{WeightHistoryCalculator._format_number(abs(percent_change))}% "
                f"weight {direction}, "
                f"{WeightHistoryCalculator._format_number(abs(change_lb))} lbs "
                f"over {elapsed_timeframe} to latest weight",
            )
        return "\n".join(lines)

    @staticmethod
    def format_elapsed_months(latest_date: date, previous_date: date) -> str:
        """Return a calendar-aware elapsed duration expressed in months."""
        if previous_date >= latest_date:
            message = "Previous weight date must be earlier than latest weight date"
            raise ValueError(message)
        whole_months = (latest_date.year - previous_date.year) * 12 + (
            latest_date.month - previous_date.month
        )
        anniversary = WeightHistoryCalculator._add_months(
            previous_date,
            whole_months,
        )
        if anniversary > latest_date:
            whole_months -= 1
            anniversary = WeightHistoryCalculator._add_months(
                previous_date,
                whole_months,
            )
        next_anniversary = WeightHistoryCalculator._add_months(
            previous_date,
            whole_months + 1,
        )
        interval_days = (next_anniversary - anniversary).days
        partial_month = (latest_date - anniversary).days / interval_days
        elapsed_months = whole_months + partial_month
        rounded_months = math.floor(elapsed_months + 0.5)
        if rounded_months < 1:
            return "<1 month"
        unit = "month" if rounded_months == 1 else "months"
        return f"{rounded_months} {unit}"

    @staticmethod
    def _absolute_percent_change(
        latest_weight_lb: float,
        previous_weight_lb: float,
    ) -> float:
        WeightHistoryCalculator._validate_weight(latest_weight_lb)
        WeightHistoryCalculator._validate_weight(previous_weight_lb)
        return abs((latest_weight_lb - previous_weight_lb) / previous_weight_lb * 100)

    @staticmethod
    def _validated_dated_weights(
        weights: list[PersonWeight],
    ) -> list[PersonWeight]:
        dated_weights = [weight for weight in weights if weight.measured_at is not None]
        if not dated_weights:
            message = "At least one weight with a measurement date is required"
            raise ValueError(message)
        for weight in dated_weights:
            WeightHistoryCalculator._validate_weight(weight.weight_lb)
        return dated_weights

    @staticmethod
    def _validate_weight(weight_lb: float) -> None:
        if weight_lb <= 0:
            message = "Weight values must be greater than zero"
            raise ValueError(message)

    @staticmethod
    def _measurement_date(weight: PersonWeight) -> datetime:
        measured_at: object = weight.measured_at
        if measured_at is None:
            message = "Weight must include a measurement date"
            raise ValueError(message)
        try:
            return _DATETIME_ADAPTER.validate_python(measured_at)
        except ValidationError as error:
            message = "Weight must include a valid measurement date"
            raise ValueError(message) from error

    @staticmethod
    def _sort_key(weight: PersonWeight) -> tuple[datetime, int]:
        return WeightHistoryCalculator._measurement_date(weight), weight.id or -1

    @staticmethod
    def _format_number(value: float) -> str:
        return f"{value:.2f}".rstrip("0").rstrip(".")


__all__ = ["WeightHistoryCalculator"]
