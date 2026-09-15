"""Food/formula vocabulary shared by cloud-api's Food catalog and engine's models."""

from __future__ import annotations

from enum import StrEnum


class LiquidConsistency(StrEnum):
    """Documented liquid/food texture thickness for dysphagia management."""

    THIN = "thin"
    SLIGHTLY_THICK = "slightly_thick"
    MILDLY_THICK = "mildly_thick"
    MODERATELY_THICK = "moderately_thick"
    EXTREMELY_THICK = "extremely_thick"


class PackageType(StrEnum):
    """Documented enteral formula package type."""

    READY_TO_HANG = "ready_to_hang"
    CARTON = "carton"
    BOTTLE = "bottle"
    CAN = "can"


__all__ = ["LiquidConsistency", "PackageType"]
