from __future__ import annotations

import pytest

from ntk.domain.convert import Convert

# ruff: noqa: S101


@pytest.mark.parametrize(
    ("inches", "expected"),
    [
        (0, 0.0),
        (1, 2.54),
        (10, 25.4),
        (-5, -12.7),
    ],
)
def test_to_cm(inches: int, expected: float) -> None:
    assert Convert.to_cm(inches) == expected


@pytest.mark.parametrize(
    ("lbs", "expected"),
    [
        (0, 0.0),
        (2.2, 1.0),
        (220, 100.0),
        (-11, -5.0),
    ],
)
def test_to_kg(lbs: float, expected: float) -> None:
    assert Convert.to_kg(lbs) == expected


@pytest.mark.parametrize(
    ("inches", "expected"),
    [
        (0, 0.0),
        (39, 0.99),
        (100, 2.54),
        (-10, -0.25),
    ],
)
def test_to_meters(inches: int, expected: float) -> None:
    assert Convert.to_meters(inches) == expected
