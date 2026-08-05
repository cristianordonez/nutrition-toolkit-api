from __future__ import annotations


class Convert:
    """Handles converting units of measurement."""

    @staticmethod
    def to_cm(inches: float) -> float:
        """Convert inches to cm.

        :param inches: number of inches (float)
        :return: cm conversion (float)
        """
        return round(float(inches) * 2.54, 2)

    @staticmethod
    def to_kg(lbs: float) -> float:
        """Convert lbs to kg.

        :param lbs: number of lbs (float)
        :return: kg (float)
        """
        return round(float(lbs) / 2.2, 2)

    @staticmethod
    def to_meters(inches: float) -> float:
        """Convert inches to meters.

        :param inches: number of inches (float)
        :return: meters (float)
        """
        return round(float(inches) * 0.0254, 2)
