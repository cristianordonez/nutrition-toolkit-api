# noqa: I002
"""SQL models for foods and nutrients."""

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


class FoodType(StrEnum):
    FOOD = "food"
    ORAL_SUPPLEMENT = "oral_supplement"
    ENTERAL_FORMULA = "enteral_formula"


class FoodSourceType(StrEnum):
    USDA_BRANDED = "usda_branded"
    USDA_FNDDS = "usda_fndds"
    USDA_FOUNDATION = "usda_foundation"
    USDA_SR_LEGACY = "usda_sr_legacy"
    FATSECRET = "fatsecret"
    MANUFACTURER = "manufacturer"
    INTERNAL = "internal"


class FoodCategorySource(StrEnum):
    USDA = "usda"
    FATSECRET = "fatsecret"
    INTERNAL = "internal"


class ImportMethod(StrEnum):
    API = "api"
    MANUAL = "manual"


class LiquidConsistency(StrEnum):
    THIN = "thin"
    SLIGHTLY_THICK = "slightly_thick"
    MILDLY_THICK = "mildly_thick"
    MODERATELY_THICK = "moderately_thick"
    EXTREMELY_THICK = "extremely_thick"


class PackageType(StrEnum):
    READY_TO_HANG = "ready_to_hang"
    CARTON = "carton"
    BOTTLE = "bottle"
    CAN = "can"


class NutrientClassification(StrEnum):
    MACRONUTRIENT = "macronutrient"
    VITAMIN = "vitamin"
    MINERAL = "mineral"


class FoodCategory(SQLModel, table=True):
    """A category containing foods."""

    __tablename__ = "food_category"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    source: FoodCategorySource | None = None
    external_id: str | None = None
    foods: list["Food"] = Relationship(back_populates="category")


class Food(SQLModel, table=True):
    """A food with an assigned category and nutrient values."""

    __tablename__ = "food"

    id: int | None = Field(default=None, primary_key=True)
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_id",
            name="uq_food_source",
        ),
    )
    name: str
    food_type: FoodType
    source_type: FoodSourceType
    import_method: ImportMethod
    source_id: str | None = None
    brand: str | None = None
    brand_owner: str | None = None
    gtin_upc: str | None = None
    ingredients: str | None = None
    serving_size: float | None = None
    serving_unit: str | None = None
    liquid_consistency: LiquidConsistency | None = None
    package_type: PackageType | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    category_id: int | None = Field(
        default=None,
        foreign_key="food_category.id",
    )
    category: FoodCategory | None = Relationship(back_populates="foods")
    nutrients: list["FoodNutrient"] = Relationship(back_populates="food")
    source_published_at: date | None = None


class Nutrient(SQLModel, table=True):
    """A nutrient definition."""

    __tablename__ = "nutrient"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    number: int
    unit_name: str
    rank: int
    classification: NutrientClassification | None = None
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


class FoodSyncState(SQLModel, table=True):
    """Persist progress for a paginated external food synchronization."""

    __tablename__ = "food_sync_state"

    id: int | None = Field(default=None, primary_key=True)
    source: FoodSourceType = Field(
        unique=True,
        index=True,
    )
    last_completed_page: int = Field(default=0, ge=0)
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
