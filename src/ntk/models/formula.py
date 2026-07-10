"""Contains models that will represent a single EN formula."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field


class Nutrition(BaseModel):
    """Nutrition info for the parent model."""

    serving_size: int = Field(description="mL per serving")
    cal: int = Field(description="kcal per serving")
    protein: float = Field(description="grams of protein per serving")
    fat: float = Field(description="grams of fat per serving")
    carbs: float = Field(description="grams of carbs per serving")
    water: int = Field(description="free water (mL) per serving")


class Formula(BaseModel):
    """Represents single EN formula."""

    name: str = Field(description="Name of formula")
    consistency: typing.Literal["thin", "nectar", "honey", "pudding"] = Field(
        description="Thickness tolerated",
    )
    nutrition: Nutrition
