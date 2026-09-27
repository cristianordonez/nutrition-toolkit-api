"""List the enteral formulas a tube-feed order can name on this device."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from engine.controllers.base import BaseController
from engine.controllers.session import controller_session
from engine.models.base import ConsoleRenderableModel
from engine.models.output import Output
from engine.repositories.enteral_formula_repo import EnteralFormulaRepo

if typing.TYPE_CHECKING:
    from sqlmodel import Session

    from engine.models.sql.enteral_formula import EnteralFormula

#: FoodData Central nutrient number for energy, used to derive caloric density.
_ENERGY_NUTRIENT_NUMBER = 1008


class FormulaListOptions(BaseModel):
    """Options for listing enteral formulas."""


class FormulaSummary(BaseModel):
    """One selectable formula product.

    Carries the fields a caller needs to build a picker: ``name`` is the exact
    value the calculator resolves, and ``package_type`` lets a caller offer only
    the products that suit the schedule being ordered -- the calculator looks
    for ready-to-hang on a continuous feed and cartons on a bolus feed.
    """

    name: str = Field(description="Exact catalog name to pass to the calculator")
    brand: str
    package_type: str
    serving_size: float
    serving_unit: str
    kcal_per_ml: float | None = Field(
        default=None,
        description="Caloric density, or null when energy is not documented",
    )


class FormulaListResult(ConsoleRenderableModel):
    """Every formula persisted on this device."""

    formulas: list[FormulaSummary]

    def to_console(self) -> str:
        """Render the formulas as formatted JSON."""
        return self.model_dump_json(indent=2)


class FormulaListController(BaseController):
    """Return every enteral formula in the local reference catalog."""

    name = "formulas"
    help = "List available enteral formulas"
    options_model = FormulaListOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(self, options: FormulaListOptions) -> Output[FormulaListResult]:
        """Return the persisted formula catalog."""
        del options
        with controller_session(self.session) as session:
            formulas = [
                self._summarize(row) for row in EnteralFormulaRepo(session).get_all()
            ]
        return Output(
            result=FormulaListResult(formulas=formulas),
            controller=self.name,
            exit_code=0,
        )

    @staticmethod
    def _summarize(row: EnteralFormula) -> FormulaSummary:
        """Flatten one formula, deriving its caloric density for display."""
        energy = next(
            (
                nutrient.amount
                for nutrient in row.nutrients
                if nutrient.number == _ENERGY_NUTRIENT_NUMBER
            ),
            None,
        )
        return FormulaSummary(
            name=row.name,
            brand=row.brand,
            package_type=row.package_type.value,
            serving_size=row.serving_size,
            serving_unit=row.serving_unit,
            kcal_per_ml=(
                round(energy / row.serving_size, 2)
                if energy is not None and row.serving_size
                else None
            ),
        )


__all__ = [
    "FormulaListController",
    "FormulaListOptions",
    "FormulaListResult",
    "FormulaSummary",
]
