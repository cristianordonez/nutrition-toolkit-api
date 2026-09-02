# noqa: I002
"""SQL models for foods and nutrients."""

from datetime import UTC, datetime

from sqlmodel import Field, Relationship, SQLModel


class FoodCategory(SQLModel, table=True):
    """A category containing foods."""

    __tablename__ = "food_category"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    foods: list["Food"] = Relationship(back_populates="category")


class Food(SQLModel, table=True):
    """A food with an assigned category and nutrient values."""

    __tablename__ = "food"

    id: int | None = Field(default=None, primary_key=True)
    description: str
    category_id: int = Field(foreign_key="food_category.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    category: FoodCategory = Relationship(back_populates="foods")
    nutrients: list["FoodNutrient"] = Relationship(back_populates="food")


class Nutrient(SQLModel, table=True):
    """A nutrient definition."""

    __tablename__ = "nutrient"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    number: int
    unit_name: str
    rank: int
    foods: list["FoodNutrient"] = Relationship(back_populates="nutrient")


class FoodNutrient(SQLModel, table=True):
    """A nutrient amount associated with a food."""

    __tablename__ = "food_nutrient"

    id: int | None = Field(default=None, primary_key=True)
    food_id: int = Field(foreign_key="food.id")
    nutrient_id: int = Field(foreign_key="nutrient.id")
    amount: float
    food: Food = Relationship(back_populates="nutrients")
    nutrient: Nutrient = Relationship(back_populates="foods")
