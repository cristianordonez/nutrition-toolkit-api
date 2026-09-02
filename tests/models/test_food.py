from __future__ import annotations

from datetime import UTC

from ntk.models.sql.food import Food, FoodCategory, FoodNutrient, Nutrient

DEFAULT_AMOUNT = 20.0


def test_food_models_create_relationship_ready_entities() -> None:
    category = FoodCategory(id=1, name="Supplements")
    food = Food(id=2, description="Nutrition shake", category_id=1)
    nutrient = Nutrient(id=3, name="Protein", number=203, unit_name="g", rank=1)
    amount = FoodNutrient(
        food_id=2,
        nutrient_id=3,
        amount=20.0,
    )

    assert category.name == "Supplements"
    assert food.created_at.tzinfo is UTC
    assert food.updated_at.tzinfo is UTC
    assert nutrient.unit_name == "g"
    assert amount.amount == DEFAULT_AMOUNT
