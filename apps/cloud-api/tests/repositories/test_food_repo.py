from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine, select

import api.models.sql  # noqa: F401
from api.models.sql.food import Food, FoodNutrient, FoodSourceType, FoodSyncState
from api.repositories.food_repo import FoodRepo
from api.services.nutrition_data.usda_transformer import (
    USDAFoodRecord,
    USDANutrientRecord,
)


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
