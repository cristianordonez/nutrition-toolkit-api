"""Convert USDA FoodData Central responses into persistence-ready records."""

from __future__ import annotations

import typing

from pydantic import BaseModel, ConfigDict, Field


class USDANutrientRecord(BaseModel):
    """Normalized nutrient value from either abridged or full USDA data."""

    model_config = ConfigDict(frozen=True)

    number: int
    name: str
    unit_name: str
    amount: float
    rank: int = 0


class USDAFoodRecord(BaseModel):
    """Normalized USDA food ready for repository persistence."""

    model_config = ConfigDict(frozen=True)

    fdc_id: int
    description: str
    data_type: str
    publication_date: str | None = None
    category_name: str
    nutrients: list[USDANutrientRecord] = Field(default_factory=list)


class USDAResponseTransformer:
    """Normalize the varying USDA food schemas into one application shape."""

    @classmethod
    def transform_many(
        cls,
        payloads: typing.Iterable[dict[str, typing.Any]],
    ) -> list[USDAFoodRecord]:
        """Transform a sequence of full USDA food responses."""
        return [cls.transform(payload) for payload in payloads]

    @classmethod
    def transform(cls, payload: dict[str, typing.Any]) -> USDAFoodRecord:
        """Transform one full or abridged USDA food response."""
        data_type = str(payload.get("dataType") or "Unknown")
        category_name = cls._category_name(payload, fallback=data_type)
        nutrients = cls._nutrients(payload.get("foodNutrients", []))
        return USDAFoodRecord(
            fdc_id=int(payload["fdcId"]),
            description=str(payload["description"]).strip(),
            data_type=data_type,
            publication_date=cls._optional_string(payload.get("publicationDate")),
            category_name=category_name,
            nutrients=nutrients,
        )

    @staticmethod
    def _category_name(payload: dict[str, typing.Any], *, fallback: str) -> str:
        category = payload.get("foodCategory")
        if isinstance(category, dict):
            description = category.get("description")
            if description:
                return str(description).strip()
        branded_category = payload.get("brandedFoodCategory")
        if branded_category:
            return str(branded_category).strip()
        return fallback

    @classmethod
    def _nutrients(cls, raw_nutrients: object) -> list[USDANutrientRecord]:
        if not isinstance(raw_nutrients, list):
            return []
        nutrients: dict[tuple[int, str], USDANutrientRecord] = {}
        for raw_nutrient in raw_nutrients:
            nutrient = cls._nutrient(raw_nutrient)
            if nutrient is not None:
                nutrients[(nutrient.number, nutrient.unit_name)] = nutrient
        return list(nutrients.values())

    @staticmethod
    def _nutrient(raw_nutrient: object) -> USDANutrientRecord | None:
        if not isinstance(raw_nutrient, dict):
            return None
        nested = raw_nutrient.get("nutrient")
        metadata = nested if isinstance(nested, dict) else raw_nutrient
        number = metadata.get("number")
        name = metadata.get("name")
        unit_name = metadata.get("unitName")
        amount = raw_nutrient.get("amount")
        if number is None or not name or not unit_name or amount is None:
            return None
        return USDANutrientRecord(
            number=int(number),
            name=str(name).strip(),
            unit_name=str(unit_name).strip(),
            amount=float(amount),
            rank=int(metadata.get("rank") or 0),
        )

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


__all__ = ["USDAFoodRecord", "USDANutrientRecord", "USDAResponseTransformer"]
