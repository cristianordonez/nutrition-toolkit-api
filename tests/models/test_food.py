from __future__ import annotations

from datetime import UTC

from ntk.models.food import Food, FoodCategory, FoodNutrient, Nutrient

DEFAULT_AMOUNT = 20.0


def test_food_models_create_relationship_ready_entities() -> None:
    category = FoodCategory(name="Supplements")
    food = Food(description="Nutrition shake", category_id=category.id)
    nutrient = Nutrient(name="Protein", number=203, unit_name="g", rank=1)
    amount = FoodNutrient(
        food_id=food.id,
        nutrient_id=nutrient.id,
        amount=20.0,
    )

    assert category.name == "Supplements"
    assert food.created_at.tzinfo is UTC
    assert food.updated_at.tzinfo is UTC
    assert nutrient.unit_name == "g"
    assert amount.amount == DEFAULT_AMOUNT
