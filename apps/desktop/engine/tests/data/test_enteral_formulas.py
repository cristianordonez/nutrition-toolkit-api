from __future__ import annotations

from engine.data.enteral_formulas import (
    DEFAULT_FORMULA_CATALOG,
    Formula,
    FormulaNutrientAmount,
    LocalFormulaCatalog,
)
from ntk.models.food_vocab import PackageType

_DEFAULT_FORMULA_COUNT = 19


def test_default_catalog_has_the_expected_formula_count() -> None:
    assert len(DEFAULT_FORMULA_CATALOG) == _DEFAULT_FORMULA_COUNT


def test_search_enteral_formulas_filters_query_and_package_type() -> None:
    imitation = Formula(
        name="Jevity imitation",
        brand="Generic",
        package_type=PackageType.CARTON,
        serving_size=250,
        nutrients=(
            FormulaNutrientAmount(
                number=1008,
                name="Energy",
                unit_name="kcal",
                amount=250,
            ),
        ),
    )
    catalog = LocalFormulaCatalog((*DEFAULT_FORMULA_CATALOG, imitation))

    formulas = catalog.search_enteral_formulas(
        "jevity",
        package_type=PackageType.READY_TO_HANG,
    )

    assert formulas
    assert all(
        formula.package_type is PackageType.READY_TO_HANG for formula in formulas
    )
    assert all("jevity" in formula.name.casefold() for formula in formulas)
    assert imitation not in formulas


def test_search_enteral_formulas_returns_empty_for_unknown_query() -> None:
    catalog = LocalFormulaCatalog()

    assert catalog.search_enteral_formulas("no-such-formula") == []
