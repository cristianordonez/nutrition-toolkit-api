from __future__ import annotations

from ntk.services.nutrition_data.usda_transformer import USDAResponseTransformer


def test_transformer_converts_full_usda_food_response() -> None:
    record = USDAResponseTransformer.transform(
        {
            "fdcId": 123,
            "description": "Alaska Pollock, raw",
            "dataType": "Foundation",
            "publicationDate": "04/30/2026",
            "foodCategory": {"description": "Finfish and Shellfish Products"},
            "foodNutrients": [
                {
                    "amount": 17.3,
                    "nutrient": {
                        "number": "203",
                        "name": "Protein",
                        "unitName": "g",
                        "rank": 600,
                    },
                },
            ],
        },
    )

    assert record.fdc_id == 123  # noqa: PLR2004
    assert record.category_name == "Finfish and Shellfish Products"
    assert record.nutrients[0].number == 203  # noqa: PLR2004
    assert record.nutrients[0].amount == 17.3  # noqa: PLR2004


def test_transformer_accepts_abridged_nutrients_and_branded_category() -> None:
    record = USDAResponseTransformer.transform(
        {
            "fdcId": 456,
            "description": "Nutrition shake",
            "dataType": "Branded",
            "brandedFoodCategory": "Nutritional Beverages",
            "foodNutrients": [
                {
                    "number": "203",
                    "name": "Protein",
                    "unitName": "G",
                    "amount": 20,
                },
            ],
        },
    )

    assert record.category_name == "Nutritional Beverages"
    assert record.nutrients[0].rank == 0
