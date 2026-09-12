from __future__ import annotations

import typing
from math import ceil, isclose

from pydantic import BaseModel

from ntk.models.sql.food import Food, PackageType

if typing.TYPE_CHECKING:
    from ntk.models.sql.clinical.enteral_feeding import PersonEnteralFeeding
    from ntk.repositories.food_repo import FoodRepo


class FreeWaterFlush(BaseModel):
    """Free water flush volume and frequency."""

    total_volume_ml: int
    rate_ml_per_hr: int | None = None
    duration_hours: int | None = None
    n_bolus_flushes: int | None = None
    pre_post_bolus_flush: bool | None = None
    pre_post_bolus_volume_ml: int | None = None


class ProteinSupplementContribution(BaseModel):
    """Daily nutrition supplied by an optional protein supplement."""

    kcal_per_day: float = 0
    protein_per_day_g: float = 0
    fluids_per_day_ml: float = 0


class FeedingSchedule(BaseModel):
    """Details shared by continuous and bolus administration schedules."""

    feeding_route: str = "PEG"
    protein_supplement: ProteinSupplementContribution | None = None


class ContinuousFeedingSchedule(FeedingSchedule):
    """Administration details for a continuous enteral feeding."""

    duration_hours: int = 18
    start_time: str = "4pm"
    starting_rate_ml_per_hr: int | None = None
    rate_increase_ml_per_hr: int | None = None


class BolusFeedingSchedule(FeedingSchedule):
    """Administration details for intermittent enteral feedings."""

    n_bolus_feeds: int


class TubeFeedResults(BaseModel):
    """Results of tube feed calculation."""

    formula: Food
    formula_display_name: str
    total_volume_ml: int
    rate_ml_per_hr: int | None = None
    duration_hours: int | None = None
    feeding_route: str | None = None
    start_time: str | None = None
    starting_rate_ml_per_hr: int | None = None
    rate_increase_ml_per_hr: int | None = None
    n_bolus_feeds: int | None = None
    volume_per_bolus_ml: int | None = None
    kcal_per_day: int
    protein_per_day_g: float
    fluids_per_day_ml: float
    free_water_flush: FreeWaterFlush | None = None
    protein_supplement: ProteinSupplementContribution | None = None
    total_kcal_per_day: float
    total_protein_per_day_g: float
    total_fluids_per_day_ml: float

    def to_console(self) -> str:
        """Render the calculated continuous or bolus tube-feed order."""
        order = (
            self._bolus_to_console()
            if self.n_bolus_feeds is not None
            else self._continuous_to_console()
        )
        return f"{order} {self._nutrition_summary()}"

    def _nutrition_summary(self) -> str:
        """Render combined nutrition without weight-based ratios."""
        sources = ["TF"]
        if self.free_water_flush is not None:
            sources.append("FWF")
        if self.protein_supplement is not None:
            sources.append("Protein supplement")
        source_text = " + ".join(sources)
        verb = "are" if len(sources) > 1 else "is"
        return (
            f"{source_text} {verb} providing res with "
            f"{self.total_kcal_per_day:g} kcal, "
            f"{self.total_protein_per_day_g:g} g PRO and "
            f"{self.total_fluids_per_day_ml:g} mls fluids."
        )

    def _bolus_to_console(self) -> str:
        """Render a bolus tube-feed order."""
        if self.volume_per_bolus_ml is None or self.feeding_route is None:
            return "Incomplete bolus tube-feed results."
        order = (
            f"Enteral feeding {self.formula_display_name} "
            f"{self.volume_per_bolus_ml} ml via {self.feeding_route.upper()} "
            f"{self.n_bolus_feeds} times daily. "
            "AND every day shift document total volume infused in 24 hrs "
            f"({self.total_volume_ml} ml)."
        )
        flush = self.free_water_flush
        if flush is not None and flush.pre_post_bolus_volume_ml is not None:
            order += (
                f" FWF {flush.pre_post_bolus_volume_ml} ml before and after "
                f"each bolus to provide TV {flush.total_volume_ml} mls."
            )
        return order

    def _continuous_to_console(self) -> str:
        """Render a continuous tube-feed order."""
        if (
            self.rate_ml_per_hr is None
            or self.feeding_route is None
            or self.start_time is None
        ):
            return "Incomplete continuous tube-feed results."
        order = (
            f"Rec {self.formula_display_name} "
            f"@ {self.rate_ml_per_hr} ml/hr "
            f"via {self.feeding_route.upper()} up at {self.start_time}. "
        )
        if (
            self.starting_rate_ml_per_hr is not None
            and self.rate_increase_ml_per_hr is not None
            and self.starting_rate_ml_per_hr < self.rate_ml_per_hr
        ):
            order += (
                f"START AT {self.starting_rate_ml_per_hr} ML/HR. "
                f"INCREASE BY {self.rate_increase_ml_per_hr} ML EVERY HOUR "
                f"UNTIL {self.rate_ml_per_hr}ML/HR. "
            )
        order += (
            "AND every day shift document total volume infused in 24 hrs "
            f"({self.total_volume_ml} ml)."
        )
        if self.free_water_flush is not None:
            order += (
                f" FWF @ {self.free_water_flush.rate_ml_per_hr} ml/hr "
                "to provide TV "
                f"{self.free_water_flush.total_volume_ml} mls."
            )
        return order


class TubeFeedDailyTotals(BaseModel):
    """Shared daily nutrition totals before selecting a delivery schedule."""

    formula: Food
    formula_display_name: str
    total_volume_ml: int
    kcal_per_day: int
    protein_per_day_g: float
    fluids_per_day_ml: float
    flush_volume_ml: int
    protein_supplement: ProteinSupplementContribution | None
    total_kcal_per_day: float
    total_protein_per_day_g: float
    total_fluids_per_day_ml: float


class ExistingTubeFeedNutrition(BaseModel):
    """Deterministic daily nutrition provided by a documented feeding order."""

    formula_display_name: str
    feeding_method: str | None
    formula_volume_ml_day: float
    formula_kcal_day: int
    formula_protein_g_day: float
    formula_water_ml_day: float
    flush_water_ml_day: float
    total_water_ml_day: float


class TubeFeedCalculator:
    """Provide stateless tube-feed methods suitable for agent tools."""

    def __init__(
        self,
        food_repo: FoodRepo,
    ) -> None:
        """Service handles tube feed calculations.

        :param food_repo: Food repo
        """
        self.food_repo = food_repo

    def find_formula(
        self,
        query: str,
        *,
        package_type: PackageType,
        package_volume_ml: int | None = None,
        caloric_density_kcal_per_ml: float | None = None,
    ) -> Food:
        """Return one uniquely matching enteral formula product."""
        matches = list(
            self.food_repo.search_enteral_formulas(
                query,
                package_type=package_type,
            ),
        )
        if package_volume_ml is not None:
            matches = [
                formula
                for formula in matches
                if formula.serving_size == package_volume_ml
                and formula.serving_unit == "mL"
            ]
        if caloric_density_kcal_per_ml is not None:
            matches = [
                formula
                for formula in matches
                if isclose(
                    self._caloric_density(formula),
                    caloric_density_kcal_per_ml,
                    abs_tol=0.01,
                )
            ]
        if not matches:
            volume = (
                f", {package_volume_ml} mL" if package_volume_ml is not None else ""
            )
            density = (
                f", {caloric_density_kcal_per_ml:g} kcal/mL"
                if caloric_density_kcal_per_ml is not None
                else ""
            )
            msg = f"Formula not found: {query} ({package_type.value}{volume}{density})"
            raise ValueError(msg)
        if len(matches) > 1:
            choices = "; ".join(self._formula_choice(formula) for formula in matches)
            msg = f"Multiple formulas matched '{query}'. Choices: {choices}."
            raise ValueError(msg)
        return matches[0]

    def calculate(  # noqa: PLR0913
        self,
        energy_needs: tuple[int, int],
        formula: str,
        *,
        package_type: PackageType | None = None,
        package_volume_ml: int | None = None,
        caloric_density_kcal_per_ml: float | None = None,
        fluid_target_ml_per_day: float | None = None,
        free_water_flush_target_ml_per_day: int | None = None,
        schedule: ContinuousFeedingSchedule | BolusFeedingSchedule | None = None,
    ) -> TubeFeedResults:
        """Calculate daily nutrition and the selected tube-feed delivery method."""
        schedule = schedule or ContinuousFeedingSchedule()
        selected_package_type = package_type or (
            PackageType.CARTON
            if isinstance(schedule, BolusFeedingSchedule)
            else PackageType.READY_TO_HANG
        )
        formula_model = self.find_formula(
            formula,
            package_type=selected_package_type,
            package_volume_ml=package_volume_ml,
            caloric_density_kcal_per_ml=caloric_density_kcal_per_ml,
        )
        calories_per_ml = self._caloric_density(formula_model)
        main_energy_needs = self._main_energy_needs(energy_needs)
        total_volume_ml = int(round(main_energy_needs / calories_per_ml, -2))
        kcal_per_day, protein_per_day_g, fluids_per_day_ml = self.calculate_nutrition(
            formula_model,
            total_volume_ml,
        )
        supplement = schedule.protein_supplement
        supplement_kcal = supplement.kcal_per_day if supplement is not None else 0
        supplement_protein = (
            supplement.protein_per_day_g if supplement is not None else 0
        )
        supplement_fluids = (
            supplement.fluids_per_day_ml if supplement is not None else 0
        )
        if free_water_flush_target_ml_per_day is not None:
            flush_volume_ml = free_water_flush_target_ml_per_day
        else:
            effective_fluid_target = (
                fluid_target_ml_per_day
                if fluid_target_ml_per_day is not None
                else kcal_per_day
            )
            fluids_needed_for_flush = max(
                effective_fluid_target - fluids_per_day_ml - supplement_fluids,
                0,
            )
            flush_volume_ml = int(round(fluids_needed_for_flush, -2))
        totals = TubeFeedDailyTotals(
            formula=formula_model,
            formula_display_name=self._formula_display_name(
                formula_model,
                calories_per_ml,
            ),
            total_volume_ml=total_volume_ml,
            kcal_per_day=kcal_per_day,
            protein_per_day_g=protein_per_day_g,
            fluids_per_day_ml=fluids_per_day_ml,
            flush_volume_ml=flush_volume_ml,
            protein_supplement=supplement,
            total_kcal_per_day=kcal_per_day + supplement_kcal,
            total_protein_per_day_g=protein_per_day_g + supplement_protein,
            total_fluids_per_day_ml=(
                fluids_per_day_ml + flush_volume_ml + supplement_fluids
            ),
        )
        if isinstance(schedule, BolusFeedingSchedule):
            return self.calculate_bolus_tube_feed(totals, schedule)
        return self.calculate_continuous_tube_feed(totals, schedule)

    def calculate_nutrition(
        self,
        formula: Food,
        total_volume_ml: int,
    ) -> tuple[int, float, float]:
        """Calculate the nutrition provided by the tube feed."""
        if formula.serving_size is None or formula.serving_size <= 0:
            msg = f"Formula has no valid serving size: {formula.name}"
            raise ValueError(msg)
        serving_size_multiplier = total_volume_ml / formula.serving_size
        nutrient_amounts = {
            food_nutrient.nutrient.number: food_nutrient.amount
            for food_nutrient in formula.nutrients
        }
        required_nutrients = {
            "energy": 1008,
            "protein": 1003,
            "free water": 1051,
        }
        missing = [
            name
            for name, number in required_nutrients.items()
            if number not in nutrient_amounts
        ]
        if missing:
            msg = f"Formula is missing required nutrients: {', '.join(missing)}"
            raise ValueError(msg)
        return (
            round(nutrient_amounts[1008] * serving_size_multiplier),
            round(nutrient_amounts[1003] * serving_size_multiplier, 1),
            round(nutrient_amounts[1051] * serving_size_multiplier, 1),
        )

    def calculate_from_feeding(
        self,
        feeding: PersonEnteralFeeding,
    ) -> ExistingTubeFeedNutrition:
        """Calculate totals from a documented feeding without inventing inputs."""
        if not feeding.formula:
            message = "Enteral feeding has no documented formula"
            raise ValueError(message)
        package_type = feeding.package_type or (
            PackageType.CARTON
            if feeding.feeding_method == "bolus"
            else PackageType.READY_TO_HANG
        )
        formula = self.find_formula(
            feeding.formula,
            package_type=package_type,
            package_volume_ml=(
                round(feeding.package_volume_ml)
                if feeding.package_volume_ml is not None
                else None
            ),
            caloric_density_kcal_per_ml=feeding.caloric_density_kcal_ml,
        )
        if feeding.feeding_method == "bolus":
            if feeding.bolus_volume_ml is None or feeding.boluses_per_day is None:
                message = "Bolus feeding requires volume and feeds per day"
                raise ValueError(message)
            formula_volume = feeding.bolus_volume_ml * feeding.boluses_per_day
        else:
            if feeding.rate_ml_hr is None or feeding.hours_per_day is None:
                message = "Continuous/cyclic feeding requires rate and hours per day"
                raise ValueError(message)
            formula_volume = feeding.rate_ml_hr * feeding.hours_per_day
        kcal, protein, formula_water = self.calculate_nutrition(
            formula,
            round(formula_volume),
        )
        flush_water = 0.0
        if feeding.flush_ml is not None:
            if feeding.flush_frequency_hours is not None:
                flush_water = feeding.flush_ml * (24 / feeding.flush_frequency_hours)
            elif feeding.feeding_method == "bolus" and feeding.boluses_per_day:
                flush_water = feeding.flush_ml * feeding.boluses_per_day
            else:
                message = "Flush volume is present without a documented frequency"
                raise ValueError(message)
        return ExistingTubeFeedNutrition(
            formula_display_name=self._formula_display_name(
                formula,
                self._caloric_density(formula),
            ),
            feeding_method=(
                feeding.feeding_method.value
                if feeding.feeding_method is not None
                else None
            ),
            formula_volume_ml_day=round(formula_volume, 1),
            formula_kcal_day=kcal,
            formula_protein_g_day=protein,
            formula_water_ml_day=formula_water,
            flush_water_ml_day=round(flush_water, 1),
            total_water_ml_day=round(formula_water + flush_water, 1),
        )

    @staticmethod
    def _round_to_nearest_5(num: float) -> int:
        return 5 * round(num / 5)

    @staticmethod
    def _round_up_to_nearest_5(num: float) -> int:
        return 5 * ceil(num / 5)

    @staticmethod
    def _formula_display_name(formula: Food, calories_per_ml: float) -> str:
        brand = formula.brand or formula.name
        return f"{brand} {calories_per_ml:.1f}".upper()

    @classmethod
    def _formula_choice(cls, formula: Food) -> str:
        """Describe a matching product sufficiently for explicit selection."""
        package_type = formula.package_type.value if formula.package_type else "unknown"
        serving = (
            f"{formula.serving_size:g} {formula.serving_unit}"
            if formula.serving_size is not None and formula.serving_unit
            else "unknown volume"
        )
        density = cls._caloric_density(formula)
        return f"{formula.name} ({package_type}, {serving}, {density:g} kcal/mL)"

    def calculate_continuous_tube_feed(
        self,
        totals: TubeFeedDailyTotals,
        schedule: ContinuousFeedingSchedule,
    ) -> TubeFeedResults:
        """Calculate the rate, advancement, and flush for continuous feeding."""
        if schedule.duration_hours <= 0:
            message = "Duration must be greater than zero."
            raise ValueError(message)
        if (schedule.starting_rate_ml_per_hr is None) != (
            schedule.rate_increase_ml_per_hr is None
        ):
            message = "Starting rate and rate increase must be provided together."
            raise ValueError(message)
        if (
            schedule.starting_rate_ml_per_hr is not None
            and schedule.starting_rate_ml_per_hr <= 0
        ):
            message = "Starting rate must be greater than zero."
            raise ValueError(message)
        if (
            schedule.rate_increase_ml_per_hr is not None
            and schedule.rate_increase_ml_per_hr <= 0
        ):
            message = "Rate increase must be greater than zero."
            raise ValueError(message)
        rate_ml_per_hr = self._round_to_nearest_5(
            totals.total_volume_ml / schedule.duration_hours,
        )
        free_water_flush = None
        if totals.flush_volume_ml:
            free_water_flush = FreeWaterFlush(
                total_volume_ml=totals.flush_volume_ml,
                rate_ml_per_hr=self._round_up_to_nearest_5(
                    totals.flush_volume_ml / schedule.duration_hours,
                ),
                duration_hours=schedule.duration_hours,
            )
        return TubeFeedResults(
            formula=totals.formula,
            formula_display_name=totals.formula_display_name,
            total_volume_ml=totals.total_volume_ml,
            kcal_per_day=totals.kcal_per_day,
            protein_per_day_g=totals.protein_per_day_g,
            fluids_per_day_ml=totals.fluids_per_day_ml,
            protein_supplement=totals.protein_supplement,
            total_kcal_per_day=totals.total_kcal_per_day,
            total_protein_per_day_g=totals.total_protein_per_day_g,
            total_fluids_per_day_ml=totals.total_fluids_per_day_ml,
            rate_ml_per_hr=rate_ml_per_hr,
            duration_hours=schedule.duration_hours,
            feeding_route=schedule.feeding_route,
            start_time=schedule.start_time,
            starting_rate_ml_per_hr=(
                min(schedule.starting_rate_ml_per_hr, rate_ml_per_hr)
                if schedule.starting_rate_ml_per_hr is not None
                else None
            ),
            rate_increase_ml_per_hr=schedule.rate_increase_ml_per_hr,
            free_water_flush=free_water_flush,
        )

    def calculate_bolus_tube_feed(
        self,
        totals: TubeFeedDailyTotals,
        schedule: BolusFeedingSchedule,
    ) -> TubeFeedResults:
        """Calculate formula and pre/post flush volumes for bolus feeding."""
        if schedule.n_bolus_feeds <= 0:
            message = "Number of bolus feeds must be greater than zero."
            raise ValueError(message)
        free_water_flush = None
        if totals.flush_volume_ml:
            free_water_flush = FreeWaterFlush(
                total_volume_ml=totals.flush_volume_ml,
                n_bolus_flushes=schedule.n_bolus_feeds * 2,
                pre_post_bolus_flush=True,
                pre_post_bolus_volume_ml=self._round_up_to_nearest_5(
                    totals.flush_volume_ml / (schedule.n_bolus_feeds * 2),
                ),
            )
        return TubeFeedResults(
            formula=totals.formula,
            formula_display_name=totals.formula_display_name,
            total_volume_ml=totals.total_volume_ml,
            kcal_per_day=totals.kcal_per_day,
            protein_per_day_g=totals.protein_per_day_g,
            fluids_per_day_ml=totals.fluids_per_day_ml,
            protein_supplement=totals.protein_supplement,
            total_kcal_per_day=totals.total_kcal_per_day,
            total_protein_per_day_g=totals.total_protein_per_day_g,
            total_fluids_per_day_ml=totals.total_fluids_per_day_ml,
            feeding_route=schedule.feeding_route,
            n_bolus_feeds=schedule.n_bolus_feeds,
            volume_per_bolus_ml=round(
                totals.total_volume_ml / schedule.n_bolus_feeds,
            ),
            free_water_flush=free_water_flush,
        )

    @staticmethod
    def _main_energy_needs(energy_needs: tuple[int, int]) -> int:
        """Calculate the average of the min and max energy needs."""
        min_energy, max_energy = energy_needs
        return (min_energy + max_energy) // 2

    @staticmethod
    def calculate_tube_feed_rate(
        volume_ml: float,
        duration_hours: float,
    ) -> float:
        """Calculate the tube feed rate in mL/hr."""
        if duration_hours <= 0:
            message = "Duration must be greater than zero."
            raise ValueError(message)
        return volume_ml / duration_hours

    @staticmethod
    def calculate_tube_feed_volume(
        rate_ml_per_hr: float,
        duration_hours: float,
    ) -> float:
        """Calculate the tube feed volume in mL."""
        if duration_hours <= 0:
            message = "Duration must be greater than zero."
            raise ValueError(message)
        return rate_ml_per_hr * duration_hours

    @staticmethod
    def _caloric_density(formula: Food) -> float:
        if not formula.serving_size:
            msg = f"Formula has no serving size: {formula.name}"
            raise ValueError(msg)
        calories = next(
            (
                nutrient.amount
                for nutrient in formula.nutrients
                if nutrient.nutrient.number == 1008  # noqa: PLR2004
            ),
            None,
        )
        if calories is None:
            msg = f"Formula has no energy nutrient: {formula.name}"
            raise ValueError(msg)
        return calories / formula.serving_size
