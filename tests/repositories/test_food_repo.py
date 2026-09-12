from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine, select

import ntk.models.sql  # noqa: F401
from ntk.defaults import DEFAULT_FORMULAS
from ntk.models.sql.food import (
    Food,
    FoodNutrient,
    FoodSourceType,
    FoodSyncState,
    FoodType,
    ImportMethod,
    Nutrient,
    PackageType,
)
from ntk.repositories.food_repo import FoodRepo
from ntk.services.nutrition_data.usda_transformer import (
    USDAFoodRecord,
    USDANutrientRecord,
)

_DEFAULT_FORMULA_COUNT = 19
_NUTRIENT_COUNT = 12


def test_persist_page_upserts_foods_and_checkpoint_atomically() -> None:
    updated_amount = 18.0
    updated_page = 101
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    record = USDAFoodRecord(
        fdc_id=123,
        description="Alaska Pollock, raw",
        data_type="Foundation",
        publication_date="04/30/2026",
        category_name="Fish",
        nutrients=[
            USDANutrientRecord(
                number=203,
                name="Protein",
                unit_name="g",
                amount=17.3,
                rank=600,
            ),
        ],
    )

    with Session(engine) as session:
        repository = FoodRepo(session)
        assert repository.persist_page("usda", 100, [record]) == 1
        assert repository.get_last_completed_page("usda") == 100  # noqa: PLR2004

        food = session.exec(select(Food)).one()
        nutrient = session.exec(select(FoodNutrient)).one()
        assert food.name == "Alaska Pollock, raw"
        assert food.source_type is FoodSourceType.USDA_FOUNDATION
        assert food.source_id == "123"
        assert nutrient.amount == 17.3  # noqa: PLR2004

        updated = record.model_copy(
            update={
                "description": "Pollock, raw",
                "nutrients": [
                    record.nutrients[0].model_copy(update={"amount": updated_amount}),
                ],
            },
        )
        repository.persist_page("usda", updated_page, [updated])

        assert len(session.exec(select(Food)).all()) == 1
        assert session.exec(select(Food)).one().name == "Pollock, raw"
        assert session.exec(select(FoodNutrient)).one().amount == updated_amount
        state = session.exec(
            select(FoodSyncState).where(
                FoodSyncState.source == FoodSourceType.USDA_FOUNDATION,
            ),
        ).one()
        assert state is not None
        assert state.last_completed_page == updated_page


def test_seed_default_formulas_creates_and_updates_food_rows() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = FoodRepo(session)
        assert repository.seed_default_formulas() == _DEFAULT_FORMULA_COUNT

        foods = session.exec(select(Food)).all()
        assert len(foods) == len(DEFAULT_FORMULAS)
        assert len(session.exec(select(Nutrient)).all()) == _NUTRIENT_COUNT
        assert len(session.exec(select(FoodNutrient)).all()) == (
            _DEFAULT_FORMULA_COUNT * _NUTRIENT_COUNT
        )

        foods[0].brand_owner = "outdated"
        session.add(foods[0])
        session.commit()

        repository.seed_default_formulas()

        assert len(session.exec(select(Food)).all()) == _DEFAULT_FORMULA_COUNT
        assert len(session.exec(select(FoodNutrient)).all()) == (
            _DEFAULT_FORMULA_COUNT * _NUTRIENT_COUNT
        )
        updated_food = session.get(Food, foods[0].id)
        assert updated_food is not None
        assert updated_food.brand_owner == "Abbott Nutrition"


def test_search_enteral_formulas_filters_query_and_package_type() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = FoodRepo(session)
        repository.seed_default_formulas()
        session.add(
            Food(
                name="Jevity imitation",
                food_type=FoodType.FOOD,
                source_type=FoodSourceType.INTERNAL,
                import_method=ImportMethod.MANUAL,
                source_id="jevity-imitation",
            ),
        )
        session.commit()

        formulas = repository.search_enteral_formulas(
            "jevity",
            package_type=PackageType.READY_TO_HANG,
        )

        assert formulas
        assert all(
            formula.food_type is FoodType.ENTERAL_FORMULA for formula in formulas
        )
        assert all(
            formula.package_type is PackageType.READY_TO_HANG for formula in formulas
        )
        assert all(formula.nutrients for formula in formulas)
