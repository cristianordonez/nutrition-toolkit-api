"""Persistence operations for the enteral-formula reference catalog."""

from __future__ import annotations

import typing

from sqlmodel import col, select

from engine.data.enteral_formulas import (
    CATALOG_VERSION,
    DEFAULT_FORMULA_CATALOG,
    Formula,
    FormulaNutrientAmount,
)
from engine.models.sql.enteral_formula import EnteralFormula, EnteralFormulaNutrient

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class EnteralFormulaRepo:
    """Persist and retrieve enteral formula products."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def get_all(self) -> list[EnteralFormula]:
        """Return every formula ordered by brand, then name."""
        statement = select(EnteralFormula).order_by(
            EnteralFormula.brand,
            EnteralFormula.name,
            col(EnteralFormula.id),
        )
        return list(self.session.exec(statement).all())

    def get_by_name(self, name: str) -> EnteralFormula | None:
        """Return one formula by its exact catalog name."""
        statement = select(EnteralFormula).where(EnteralFormula.name == name)
        return self.session.exec(statement).first()

    def get_catalog(self) -> tuple[Formula, ...]:
        """Return the persisted catalog in the shape the calculator expects.

        The calculator and the tube-feed prompt both work with the frozen
        ``Formula`` dataclass, so the rows are mapped back to it here rather
        than leaking SQLModel instances up into the calculation layer.
        """
        return tuple(self._to_dataclass(row) for row in self.get_all())

    def seed_defaults(
        self,
        catalog: tuple[Formula, ...] = DEFAULT_FORMULA_CATALOG,
        *,
        version: str = CATALOG_VERSION,
    ) -> list[EnteralFormula]:
        """Idempotently seed the bundled catalog, refreshing stale rows.

        Runs on every startup. A formula already stored at ``version`` is left
        untouched so repeated launches do no writes; anything missing or from
        an older catalog is written with its nutrients replaced wholesale,
        which is how a shipped catalog update reaches an existing device.
        """
        seeded = [self._upsert(formula, version=version) for formula in catalog]
        self.session.commit()
        for row in seeded:
            self.session.refresh(row)
        return seeded

    def _upsert(self, formula: Formula, *, version: str) -> EnteralFormula:
        """Create or refresh one formula without committing."""
        existing = self.get_by_name(formula.name)
        if existing is not None and existing.catalog_version == version:
            return existing
        row = existing or EnteralFormula(name=formula.name)
        row.brand = formula.brand
        row.brand_owner = formula.brand_owner
        row.package_type = formula.package_type
        row.serving_size = formula.serving_size
        row.serving_unit = formula.serving_unit
        row.liquid_consistency = formula.liquid_consistency
        row.catalog_version = version
        # delete-orphan on the relationship removes the previous rows.
        row.nutrients = [
            EnteralFormulaNutrient(
                ordinal=ordinal,
                number=nutrient.number,
                name=nutrient.name,
                unit_name=nutrient.unit_name,
                amount=nutrient.amount,
            )
            for ordinal, nutrient in enumerate(formula.nutrients)
        ]
        self.session.add(row)
        return row

    @staticmethod
    def _to_dataclass(row: EnteralFormula) -> Formula:
        """Convert one persisted formula back into the calculator's shape."""
        return Formula(
            name=row.name,
            brand=row.brand,
            brand_owner=row.brand_owner,
            package_type=row.package_type,
            serving_size=row.serving_size,
            serving_unit=row.serving_unit,
            liquid_consistency=row.liquid_consistency,
            nutrients=tuple(
                FormulaNutrientAmount(
                    number=nutrient.number,
                    name=nutrient.name,
                    unit_name=nutrient.unit_name,
                    amount=nutrient.amount,
                )
                # The relationship is already ordered by the catalog's ordinal.
                for nutrient in row.nutrients
            ),
        )


__all__ = ["EnteralFormulaRepo"]
