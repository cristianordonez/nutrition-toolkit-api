"""Persisted enteral-formula reference catalog.

Product reference data rather than clinical records, which is why these tables
sit beside ``facility`` instead of under ``clinical/`` -- nothing here is PHI.
Rows are seeded from ``engine.data.enteral_formulas.DEFAULT_FORMULA_CATALOG``
on startup, so the device is the durable source of truth for exactly which
products a tube-feed order may name and the UI can offer that same set.
"""

from __future__ import annotations

from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

from ntk.models.food_vocab import LiquidConsistency, PackageType  # noqa: TC001


class EnteralFormulaNutrient(SQLModel, table=True):
    """One nutrient amount documented for a formula's serving size.

    Defined before ``EnteralFormula`` so the parent's ``list[...]`` annotation
    resolves against a real class at import time.
    """

    __tablename__ = "enteral_formula_nutrient"

    id: int | None = Field(default=None, primary_key=True)
    formula_id: int = Field(foreign_key="enteral_formula.id", index=True)
    # Position in the catalog's documented nutrient order, which is the order a
    # label lists them in and is not the same as ascending nutrient number.
    ordinal: int
    number: int = Field(index=True)
    name: str
    unit_name: str
    amount: float


class EnteralFormula(SQLModel, table=True):
    """One enteral formula product the on-device calculator can order."""

    __tablename__ = "enteral_formula"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    brand: str = Field(index=True)
    brand_owner: str
    package_type: PackageType = Field(index=True)
    serving_size: float
    serving_unit: str = Field(default="mL")
    liquid_consistency: LiquidConsistency
    catalog_version: str = Field(index=True)
    # Nutrients are meaningless without their formula and are replaced wholesale
    # when a newer catalog version is seeded, so they are owned outright.
    nutrients: list[EnteralFormulaNutrient] = Relationship(
        sa_relationship=relationship(
            "EnteralFormulaNutrient",
            cascade="all, delete-orphan",
            order_by="EnteralFormulaNutrient.ordinal",
        ),
    )


__all__ = ["EnteralFormula", "EnteralFormulaNutrient"]
