from __future__ import annotations

from dataclasses import replace

from sqlmodel import Session, SQLModel, create_engine, select

from engine.data.enteral_formulas import DEFAULT_FORMULA_CATALOG
from engine.models.sql.enteral_formula import EnteralFormula, EnteralFormulaNutrient
from engine.repositories.enteral_formula_repo import EnteralFormulaRepo

_NUTRIENTS_PER_FORMULA = 12


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_seeding_persists_the_bundled_catalog() -> None:
    with _session() as session:
        EnteralFormulaRepo(session).seed_defaults()

        formulas = session.exec(select(EnteralFormula)).all()
        nutrients = session.exec(select(EnteralFormulaNutrient)).all()

    assert len(formulas) == len(DEFAULT_FORMULA_CATALOG)
    assert len(nutrients) == len(DEFAULT_FORMULA_CATALOG) * _NUTRIENTS_PER_FORMULA


def test_seeding_twice_does_not_duplicate_rows() -> None:
    """Seeding runs on every startup, so a second pass must be a no-op."""
    with _session() as session:
        repository = EnteralFormulaRepo(session)
        repository.seed_defaults()
        first_ids = [formula.id for formula in repository.get_all()]

        repository.seed_defaults()
        second_ids = [formula.id for formula in repository.get_all()]

        nutrients = session.exec(select(EnteralFormulaNutrient)).all()

    assert second_ids == first_ids
    assert len(nutrients) == len(DEFAULT_FORMULA_CATALOG) * _NUTRIENTS_PER_FORMULA


def test_a_newer_catalog_version_refreshes_an_existing_formula() -> None:
    """A shipped catalog update has to reach a device that already seeded."""
    original = DEFAULT_FORMULA_CATALOG[0]
    corrected = replace(original, brand="Reformulated")

    with _session() as session:
        repository = EnteralFormulaRepo(session)
        repository.seed_defaults((original,), version="1.0.0")
        repository.seed_defaults((corrected,), version="1.1.0")

        stored = repository.get_by_name(original.name)
        assert stored is not None
        assert stored.brand == "Reformulated"
        assert stored.catalog_version == "1.1.0"
        # The refresh replaces nutrients rather than appending a second set.
        assert len(stored.nutrients) == len(original.nutrients)


def test_catalog_round_trips_back_to_the_calculator_shape() -> None:
    """The calculator works on the frozen dataclass, not on SQLModel rows."""
    with _session() as session:
        repository = EnteralFormulaRepo(session)
        repository.seed_defaults()

        catalog = repository.get_catalog()

    assert set(catalog) == set(DEFAULT_FORMULA_CATALOG)
