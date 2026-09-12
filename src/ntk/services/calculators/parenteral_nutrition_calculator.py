"""Deterministic calculations derived from parenteral nutrition prescriptions."""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from ntk.models.sql.clinical import LipidDeliveryType, PersonParenteralNutrition

_DEXTROSE_KCAL_PER_G = 3.4
_AMINO_ACID_KCAL_PER_G = 4.0
_LIPID_KCAL_PER_ML = {10.0: 1.1, 20.0: 2.0, 30.0: 3.0}
_SCHEDULE_TOLERANCE = 0.01
_DOCUMENTED_VALUE_TOLERANCE = 0.05
_MAX_HOURS_PER_DAY = 24


class ParenteralNutritionCalculationInput(BaseModel):
    """Structured PN inputs accepted by the deterministic calculator."""

    total_volume_ml: float | None = Field(default=None, gt=0)
    rate_ml_hr: float | None = Field(default=None, gt=0)
    hours_per_day: float | None = Field(default=None, gt=0, le=24)
    dextrose_g_per_l: float | None = Field(default=None, ge=0)
    amino_acid_g_per_l: float | None = Field(default=None, ge=0)
    documented_protein_g: float | None = Field(default=None, ge=0)
    documented_calories_kcal: float | None = Field(default=None, ge=0)
    lipid_delivery: LipidDeliveryType | None = None
    lipid_concentration_percent: float | None = Field(default=None, gt=0, le=100)
    lipid_total_volume_ml: float | None = Field(default=None, gt=0)
    lipid_run_time_hours: float | None = Field(default=None, gt=0, le=24)
    lipid_rate_ml_hr: float | None = Field(default=None, gt=0)
    weight_kg: float | None = Field(default=None, gt=0)


class ParenteralNutritionCalculationResult(BaseModel):
    """Derived PN values; none of these fields are source documentation."""

    total_volume_ml: float | None
    rate_ml_hr: float | None
    hours_per_day: float | None
    dextrose_g_day: float | None
    amino_acid_g_day: float | None
    calculated_protein_g_day: float | None
    dextrose_kcal_day: float | None
    amino_acid_kcal_day: float | None
    lipid_g_day: float | None
    lipid_kcal_day: float | None
    total_kcal_day: float | None
    total_fluid_ml_day: float | None
    lipid_rate_ml_hr: float | None
    gir_mg_kg_min: float | None
    documented_protein_g: float | None
    documented_calories_kcal: float | None
    missing_inputs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class ParenteralNutritionCalculator:
    """Calculate PN nutrient delivery without mutating or persisting a prescription."""

    @classmethod
    def calculate(
        cls,
        data: ParenteralNutritionCalculationInput,
    ) -> ParenteralNutritionCalculationResult:
        """Return deterministic schedule, nutrient, fluid, and GIR calculations."""
        volume, rate, hours = cls._schedule(data)
        warnings: list[str] = []
        missing: list[str] = []
        if volume is None:
            missing.append("total_volume_ml_or_rate_and_hours_per_day")

        volume_l = volume / 1000 if volume is not None else None
        dextrose_g = cls._amount_per_day(data.dextrose_g_per_l, volume_l)
        amino_acid_g = cls._amount_per_day(data.amino_acid_g_per_l, volume_l)
        if data.dextrose_g_per_l is None:
            missing.append("dextrose_g_per_l")
        if data.amino_acid_g_per_l is None:
            missing.append("amino_acid_g_per_l")

        dextrose_kcal = cls._multiply(dextrose_g, _DEXTROSE_KCAL_PER_G)
        amino_acid_kcal = cls._multiply(amino_acid_g, _AMINO_ACID_KCAL_PER_G)
        lipid_g, lipid_kcal = cls._lipids(data, warnings, missing)

        calorie_parts = (dextrose_kcal, amino_acid_kcal, lipid_kcal)
        total_kcal = (
            sum(part for part in calorie_parts if part is not None)
            if all(part is not None for part in calorie_parts)
            else None
        )
        total_fluid = volume
        if (
            total_fluid is not None
            and data.lipid_delivery is LipidDeliveryType.PIGGYBACK
            and data.lipid_total_volume_ml is not None
        ):
            total_fluid += data.lipid_total_volume_ml
        elif total_fluid is not None and data.lipid_delivery in {
            None,
            LipidDeliveryType.UNKNOWN,
        }:
            total_fluid = None

        lipid_rate = cls._lipid_rate(data)
        gir = None
        if dextrose_g is not None and data.weight_kg is not None and hours is not None:
            gir = dextrose_g * 1000 / (data.weight_kg * hours * 60)
        elif dextrose_g is not None and data.weight_kg is None:
            missing.append("weight_kg_for_gir")

        cls._compare_documented(
            "protein",
            amino_acid_g,
            data.documented_protein_g,
            warnings,
        )
        cls._compare_documented(
            "calories",
            total_kcal,
            data.documented_calories_kcal,
            warnings,
        )

        return ParenteralNutritionCalculationResult(
            total_volume_ml=cls._round(volume),
            rate_ml_hr=cls._round(rate),
            hours_per_day=cls._round(hours),
            dextrose_g_day=cls._round(dextrose_g),
            amino_acid_g_day=cls._round(amino_acid_g),
            calculated_protein_g_day=cls._round(amino_acid_g),
            dextrose_kcal_day=cls._round(dextrose_kcal),
            amino_acid_kcal_day=cls._round(amino_acid_kcal),
            lipid_g_day=cls._round(lipid_g),
            lipid_kcal_day=cls._round(lipid_kcal),
            total_kcal_day=cls._round(total_kcal),
            total_fluid_ml_day=cls._round(total_fluid),
            lipid_rate_ml_hr=cls._round(lipid_rate),
            gir_mg_kg_min=cls._round(gir),
            documented_protein_g=cls._round(data.documented_protein_g),
            documented_calories_kcal=cls._round(data.documented_calories_kcal),
            missing_inputs=tuple(dict.fromkeys(missing)),
            warnings=tuple(warnings),
        )

    @classmethod
    def calculate_from_prescription(
        cls,
        prescription: PersonParenteralNutrition,
        *,
        weight_kg: float | None = None,
    ) -> ParenteralNutritionCalculationResult:
        """Calculate from a persisted prescription without storing derived values."""
        return cls.calculate(
            ParenteralNutritionCalculationInput(
                **prescription.model_dump(
                    include=set(ParenteralNutritionCalculationInput.model_fields)
                    - {"weight_kg"},
                ),
                weight_kg=weight_kg,
            ),
        )

    @staticmethod
    def _schedule(
        data: ParenteralNutritionCalculationInput,
    ) -> tuple[float | None, float | None, float | None]:
        volume = data.total_volume_ml
        rate = data.rate_ml_hr
        hours = data.hours_per_day
        if volume is not None and rate is not None and hours is not None:
            expected = rate * hours
            difference = abs(expected - volume) / volume
            if difference > _SCHEDULE_TOLERANCE:
                message = (
                    "Documented PN volume, rate, and duration conflict: "
                    f"{rate:g} mL/hr x {hours:g} hr = {expected:g} mL, "
                    f"not {volume:g} mL"
                )
                raise ValueError(message)
            return volume, rate, hours
        if volume is not None and hours is not None:
            return volume, volume / hours, hours
        if volume is not None and rate is not None:
            derived_hours = volume / rate
            if derived_hours > _MAX_HOURS_PER_DAY:
                message = "Derived PN duration exceeds 24 hours"
                raise ValueError(message)
            return volume, rate, derived_hours
        if rate is not None and hours is not None:
            return rate * hours, rate, hours
        return volume, rate, hours

    @staticmethod
    def _amount_per_day(
        grams_per_liter: float | None,
        volume_l: float | None,
    ) -> float | None:
        if grams_per_liter is None or volume_l is None:
            return None
        return grams_per_liter * volume_l

    @staticmethod
    def _multiply(value: float | None, factor: float) -> float | None:
        return value * factor if value is not None else None

    @staticmethod
    def _lipids(
        data: ParenteralNutritionCalculationInput,
        warnings: list[str],
        missing: list[str],
    ) -> tuple[float | None, float | None]:
        if data.lipid_delivery is LipidDeliveryType.NONE:
            return 0.0, 0.0
        concentration = data.lipid_concentration_percent
        volume = data.lipid_total_volume_ml
        if data.lipid_delivery in {None, LipidDeliveryType.UNKNOWN}:
            missing.append("lipid_delivery")
        if concentration is None and volume is None:
            return None, None
        if concentration is None:
            missing.append("lipid_concentration_percent")
            return None, None
        if volume is None:
            missing.append("lipid_total_volume_ml")
            return None, None
        lipid_g = volume * concentration / 100
        kcal_per_ml = _LIPID_KCAL_PER_ML.get(concentration)
        if kcal_per_ml is None:
            warnings.append(
                "Lipid calories were not calculated for a nonstandard concentration",
            )
            return lipid_g, None
        return lipid_g, volume * kcal_per_ml

    @staticmethod
    def _lipid_rate(data: ParenteralNutritionCalculationInput) -> float | None:
        volume = data.lipid_total_volume_ml
        documented_rate = data.lipid_rate_ml_hr
        hours = data.lipid_run_time_hours
        if volume is not None and documented_rate is not None and hours is not None:
            expected = documented_rate * hours
            if abs(expected - volume) / volume > _SCHEDULE_TOLERANCE:
                message = "Documented lipid volume, rate, and duration conflict"
                raise ValueError(message)
            return documented_rate
        if volume is not None and hours is not None:
            return volume / hours
        return documented_rate

    @staticmethod
    def _compare_documented(
        label: str,
        calculated: float | None,
        documented: float | None,
        warnings: list[str],
    ) -> None:
        if calculated is None or documented is None:
            return
        denominator = max(abs(documented), 1.0)
        if abs(calculated - documented) / denominator > _DOCUMENTED_VALUE_TOLERANCE:
            warnings.append(
                f"Documented {label} differs from the deterministic calculation",
            )

    @staticmethod
    def _round(value: float | None) -> float | None:
        if value is None:
            return None
        if not math.isfinite(value):
            message = "PN calculation produced a non-finite value"
            raise ValueError(message)
        return round(value, 2)


__all__ = [
    "ParenteralNutritionCalculationInput",
    "ParenteralNutritionCalculationResult",
    "ParenteralNutritionCalculator",
]
