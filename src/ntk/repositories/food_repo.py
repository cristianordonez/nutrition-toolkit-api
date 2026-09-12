"""Persistence for normalized external food data and sync checkpoints."""

from __future__ import annotations

import typing
from datetime import UTC, date, datetime

from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload
from sqlmodel import col, delete, select

from ntk.defaults import DEFAULT_FORMULAS
from ntk.models.sql.food import (
    Food,
    FoodCategory,
    FoodCategorySource,
    FoodNutrient,
    FoodSourceType,
    FoodSyncState,
    FoodType,
    ImportMethod,
    Nutrient,
    NutrientClassification,
    PackageType,
)
from ntk.utils.misc import require_id

if typing.TYPE_CHECKING:
    from sqlmodel import Session

    from ntk.defaults import DefaultFormula
    from ntk.services.nutrition_data.usda_transformer import USDAFoodRecord


class FoodRepo:
    """Upsert USDA foods and atomically advance their page checkpoint."""

    def __init__(self, session: Session) -> None:
        """Store the database session."""
        self.session = session

    def get_last_completed_page(self, source: str) -> int:
        """Return the last page committed for an external source."""
        state = self._sync_state(self._checkpoint_source(source))
        return state.last_completed_page if state is not None else 0

    def seed_default_formulas(self) -> int:
        """Create or update every built-in enteral formula atomically."""
        try:
            for formula in DEFAULT_FORMULAS:
                self._upsert_default_formula(formula)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return len(DEFAULT_FORMULAS)

    def search_enteral_formulas(
        self,
        query: str,
        *,
        package_type: PackageType | None = None,
    ) -> list[Food]:
        """Search enteral formulas by name, brand, or manufacturer."""
        statement = (
            select(Food)
            .where(Food.food_type == FoodType.ENTERAL_FORMULA)
            .options(
                selectinload(
                    typing.cast("typing.Any", Food.nutrients),
                ).selectinload(
                    typing.cast("typing.Any", FoodNutrient.nutrient),
                ),
            )
            .order_by(col(Food.name), col(Food.serving_size))
        )
        normalized_query = " ".join(query.casefold().split())
        if normalized_query:
            statement = statement.where(
                or_(
                    func.lower(Food.name).contains(normalized_query),
                    func.lower(Food.brand).contains(normalized_query),
                    func.lower(Food.brand_owner).contains(normalized_query),
                ),
            )
        if package_type is not None:
            statement = statement.where(Food.package_type == package_type)
        return list(self.session.exec(statement))

    def persist_page(
        self,
        source: str,
        page_number: int,
        records: typing.Iterable[USDAFoodRecord],
    ) -> int:
        """Persist a complete page and its checkpoint in one transaction."""
        if page_number < 1:
            msg = "page_number must be at least 1"
            raise ValueError(msg)
        record_list = list(records)
        checkpoint_source = self._checkpoint_source(source)
        try:
            for record in record_list:
                self._upsert_food(record)
            state = self._sync_state(checkpoint_source)
            if state is None:
                state = FoodSyncState(source=checkpoint_source)
            state.last_completed_page = max(state.last_completed_page, page_number)
            state.updated_at = datetime.now(UTC)
            self.session.add(state)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return len(record_list)

    def _sync_state(self, source: FoodSourceType) -> FoodSyncState | None:
        statement = select(FoodSyncState).where(FoodSyncState.source == source)
        return self.session.exec(statement).first()

    def _upsert_food(self, record: USDAFoodRecord) -> None:
        source_type = self._food_source(record.data_type)
        source_id = str(record.fdc_id)
        food = self.session.exec(
            select(Food).where(
                Food.source_type == source_type,
                Food.source_id == source_id,
            ),
        ).first()
        category = self._category(record.category_name)
        if food is None:
            food = Food(
                name=record.description,
                food_type=FoodType.FOOD,
                source_type=source_type,
                import_method=ImportMethod.API,
                source_id=source_id,
                category_id=require_id(category.id),
                source_published_at=self._publication_date(record.publication_date),
            )
        else:
            food.name = record.description
            food.category_id = require_id(category.id)
            food.source_published_at = self._publication_date(record.publication_date)
            food.updated_at = datetime.now(UTC)
        self.session.add(food)
        self.session.flush()
        food_id = require_id(food.id)

        self.session.exec(
            delete(FoodNutrient).where(col(FoodNutrient.food_id) == food_id),
        )
        for nutrient_record in record.nutrients:
            nutrient = self._nutrient(
                nutrient_record.number,
                nutrient_record.name,
                nutrient_record.unit_name,
                nutrient_record.rank,
            )
            self.session.add(
                FoodNutrient(
                    food_id=food_id,
                    nutrient_id=require_id(nutrient.id),
                    amount=nutrient_record.amount,
                ),
            )

    def _upsert_default_formula(self, formula: DefaultFormula) -> None:
        food = self.session.exec(
            select(Food).where(
                Food.source_type == FoodSourceType.MANUFACTURER,
                Food.source_id == formula.source_id,
            ),
        ).first()
        if food is None:
            food = Food(
                name=formula.name,
                food_type=FoodType.ENTERAL_FORMULA,
                source_type=FoodSourceType.MANUFACTURER,
                import_method=ImportMethod.MANUAL,
                source_id=formula.source_id,
            )
        food.name = formula.name
        food.food_type = FoodType.ENTERAL_FORMULA
        food.import_method = ImportMethod.MANUAL
        food.brand = formula.brand
        food.brand_owner = formula.brand_owner
        food.serving_size = formula.serving_size_ml
        food.serving_unit = "mL"
        food.liquid_consistency = formula.liquid_consistency
        food.package_type = formula.package_type
        food.updated_at = datetime.now(UTC)
        self.session.add(food)
        self.session.flush()
        food_id = require_id(food.id)
        self.session.exec(
            delete(FoodNutrient).where(col(FoodNutrient.food_id) == food_id),
        )
        for nutrient_default in formula.nutrients:
            nutrient = self._nutrient(
                nutrient_default.number,
                nutrient_default.name,
                nutrient_default.unit_name,
                rank=0,
                classification=nutrient_default.classification,
            )
            self.session.add(
                FoodNutrient(
                    food_id=food_id,
                    nutrient_id=require_id(nutrient.id),
                    amount=nutrient_default.amount,
                ),
            )

    def _category(self, name: str) -> FoodCategory:
        normalized = " ".join(name.split())
        statement = select(FoodCategory).where(
            func.lower(FoodCategory.name) == normalized.casefold(),
            FoodCategory.source == FoodCategorySource.USDA,
        )
        category = self.session.exec(statement).first()
        if category is None:
            category = FoodCategory(
                name=normalized,
                source=FoodCategorySource.USDA,
            )
            self.session.add(category)
            self.session.flush()
        return category

    def _nutrient(
        self,
        number: int,
        name: str,
        unit_name: str,
        rank: int,
        classification: NutrientClassification | None = None,
    ) -> Nutrient:
        statement = select(Nutrient).where(
            Nutrient.number == number,
            func.lower(Nutrient.unit_name) == unit_name.casefold(),
        )
        nutrient = self.session.exec(statement).first()
        if nutrient is None:
            nutrient = Nutrient(
                name=name,
                number=number,
                unit_name=unit_name,
                rank=rank,
                classification=classification,
            )
            self.session.add(nutrient)
            self.session.flush()
        else:
            nutrient.name = name
            nutrient.rank = rank
            if classification is not None:
                nutrient.classification = classification
            self.session.add(nutrient)
        return nutrient

    @staticmethod
    def _food_source(data_type: str) -> FoodSourceType:
        normalized = " ".join(data_type.casefold().split())
        source_types = {
            "branded": FoodSourceType.USDA_BRANDED,
            "foundation": FoodSourceType.USDA_FOUNDATION,
            "survey (fndds)": FoodSourceType.USDA_FNDDS,
            "sr legacy": FoodSourceType.USDA_SR_LEGACY,
        }
        try:
            return source_types[normalized]
        except KeyError as error:
            msg = f"Unsupported USDA data type: {data_type!r}"
            raise ValueError(msg) from error

    @staticmethod
    def _checkpoint_source(source: str) -> FoodSourceType:
        if source.startswith("usda"):
            return FoodSourceType.USDA_FOUNDATION
        try:
            return FoodSourceType(source)
        except ValueError as error:
            msg = f"Unsupported food sync source: {source!r}"
            raise ValueError(msg) from error

    @staticmethod
    def _publication_date(value: str | None) -> date | None:
        if value is None:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return datetime.strptime(value, "%m/%d/%Y").date()  # noqa: DTZ007


__all__ = ["FoodRepo"]
