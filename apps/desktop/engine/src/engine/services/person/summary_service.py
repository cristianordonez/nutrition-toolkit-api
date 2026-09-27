"""Build concise, UI-facing summaries from complete person details."""

from __future__ import annotations

import typing

from engine.models.person_detail import PersonDetail
from engine.models.person_summary import (
    MissingPersonData,
    PersonDataCategory,
    PersonDataSummary,
    PersonSummaryField,
)

if typing.TYPE_CHECKING:
    from collections.abc import Iterable


class PersonSummaryService:
    """Describe what is and is not documented for one person."""

    @classmethod
    def build(cls, detail: PersonDetail) -> PersonDataSummary:
        """Create a bounded summary without exposing full clinical records."""
        person_id = detail.person_id
        if person_id is None:
            msg = "A persisted person ID is required to build a summary"
            raise ValueError(msg)

        overview = [
            PersonSummaryField(
                key="date_of_birth",
                label="Date of birth",
                value=(
                    f"{detail.date_of_birth.isoformat()} · age {detail.age}"
                    if detail.date_of_birth is not None and detail.age is not None
                    else (
                        detail.date_of_birth.isoformat()
                        if detail.date_of_birth is not None
                        else None
                    )
                ),
            ),
            PersonSummaryField(
                key="sex",
                label="Sex",
                value={"f": "Female", "m": "Male"}.get(
                    (detail.sex or "").casefold(),
                    detail.sex,
                ),
            ),
            PersonSummaryField(
                key="height",
                label="Height",
                value=(
                    f"{cls._number(detail.height_in)} in"
                    if detail.height_in is not None
                    else None
                ),
            ),
            PersonSummaryField(
                key="current_weight",
                label="Current weight",
                value=cls._current_weight(detail),
            ),
            PersonSummaryField(
                key="bmi",
                label="BMI",
                value=cls._bmi(detail),
            ),
            PersonSummaryField(
                key="current_diet",
                label="Current diet",
                value=cls._current_diet(detail),
            ),
            PersonSummaryField(
                key="nutrition_support",
                label="Nutrition support",
                value=cls._nutrition_support(detail),
            ),
        ]
        categories = cls._categories(detail)
        return PersonDataSummary(
            person_id=person_id,
            name=detail.name,
            person_identifier=detail.person_identifier,
            overview=overview,
            categories=categories,
            missing=cls._missing(detail),
            conflicts=[conflict.message for conflict in detail.conflicts],
        )

    @classmethod
    def _categories(cls, detail: PersonDetail) -> list[PersonDataCategory]:
        feeding_count = len(detail.enteral_feedings) + len(
            detail.parenteral_nutrition_records,
        )
        intake_count = len(detail.meal_intakes) + len(
            detail.appetite_observations,
        )
        return [
            PersonDataCategory(
                key="weights",
                label="Weight measurements",
                count=len(detail.weights),
            ),
            PersonDataCategory(
                key="diagnoses",
                label="Active diagnoses",
                count=len(detail.active_diagnoses),
                detail=cls._preview(
                    diagnosis.diagnosis for diagnosis in detail.active_diagnoses
                ),
            ),
            PersonDataCategory(
                key="medications",
                label="Active medications",
                count=len(detail.active_medications),
                detail=cls._preview(
                    medication.name for medication in detail.active_medications
                ),
            ),
            PersonDataCategory(
                key="allergies",
                label="Allergy records",
                count=len(detail.active_allergies),
                detail=cls._allergies(detail),
            ),
            PersonDataCategory(
                key="labs",
                label="Recent lab results",
                count=len(detail.labs),
                detail=cls._preview(
                    " ".join(part for part in (lab.name, lab.result, lab.unit) if part)
                    for lab in detail.labs
                ),
            ),
            PersonDataCategory(
                key="diets",
                label="Diet records",
                count=len(detail.diets),
            ),
            PersonDataCategory(
                key="intake",
                label="Intake and appetite observations",
                count=intake_count,
            ),
            PersonDataCategory(
                key="nutrition_support",
                label="Nutrition support orders",
                count=feeding_count,
            ),
            PersonDataCategory(
                key="supplements",
                label="Active supplements",
                count=len(detail.active_supplements),
                detail=cls._preview(
                    supplement.product_name for supplement in detail.active_supplements
                ),
            ),
            PersonDataCategory(
                key="nutrition_goals",
                label="Active nutrition goals",
                count=len(detail.active_nutrition_goals),
                detail=cls._preview(
                    cls._pretty(goal.goal_type)
                    for goal in detail.active_nutrition_goals
                ),
            ),
            PersonDataCategory(
                key="oral_feeding",
                label="Oral and swallowing assessments",
                count=len(detail.oral_feeding_status_history),
            ),
            PersonDataCategory(
                key="gi",
                label="GI observations",
                count=len(detail.gi_observations),
            ),
            PersonDataCategory(
                key="wounds",
                label="Wounds",
                count=len(detail.wounds),
            ),
            PersonDataCategory(
                key="edema",
                label="Edema observations",
                count=len(detail.edema),
            ),
            PersonDataCategory(
                key="food_preferences",
                label="Food preferences",
                count=len(detail.active_food_preferences),
            ),
            PersonDataCategory(
                key="clinical_notes",
                label="Clinical notes",
                count=len(detail.clinical_notes),
            ),
            PersonDataCategory(
                key="clinical_facts",
                label="Other clinical facts",
                count=len(detail.clinical_facts),
            ),
        ]

    @staticmethod
    def _missing(detail: PersonDetail) -> list[MissingPersonData]:
        missing: list[MissingPersonData] = []

        def add(condition: bool, key: str, label: str, reason: str) -> None:
            if condition:
                missing.append(
                    MissingPersonData(key=key, label=label, reason=reason),
                )

        add(
            detail.person_identifier is None,
            "person_identifier",
            "Resident identifier",
            "No external resident identifier is documented.",
        )
        add(
            detail.date_of_birth is None,
            "date_of_birth",
            "Date of birth",
            "Age and age-dependent calculations cannot be confirmed.",
        )
        add(
            detail.sex is None,
            "sex",
            "Sex",
            "Sex-dependent anthropometric calculations are unavailable.",
        )
        add(
            detail.height_in is None,
            "height",
            "Height",
            "BMI and ideal-weight calculations are unavailable.",
        )
        add(
            detail.current_weight is None,
            "current_weight",
            "Current dated weight",
            "Nutrition needs and weight status cannot be calculated reliably.",
        )
        add(
            len(detail.weights) < 2,
            "weight_history",
            "Prior weight history",
            "Weight change and clinical significance cannot be assessed.",
        )
        add(
            detail.current_diet is None,
            "current_diet",
            "Current diet order",
            "No unambiguous active diet order is documented.",
        )
        add(
            not detail.active_diagnoses,
            "diagnoses",
            "Active diagnoses",
            "No active diagnosis list is documented.",
        )
        add(
            not detail.active_medications,
            "medications",
            "Active medications",
            "No active medication list is documented.",
        )
        add(
            not detail.active_allergies,
            "allergies",
            "Allergies or explicit NKA",
            (
                "Neither allergies nor an explicit no-known-allergies record "
                "is documented."
            ),
        )
        add(
            not detail.labs,
            "labs",
            "Recent laboratory results",
            "No dated laboratory results are available.",
        )
        add(
            not detail.meal_intakes and not detail.appetite_observations,
            "intake",
            "Food intake or appetite",
            "No recent meal-intake or appetite observations are documented.",
        )
        add(
            detail.current_oral_feeding_status is None,
            "oral_feeding",
            "Oral and swallowing status",
            "No current chewing, swallowing, or aspiration assessment is documented.",
        )
        add(
            not detail.active_nutrition_goals,
            "nutrition_goals",
            "Nutrition goals",
            "No active source-supported nutrition goal is documented.",
        )
        return missing

    @classmethod
    def _current_weight(cls, detail: PersonDetail) -> str | None:
        weight = detail.current_weight
        if weight is None:
            return None
        return f"{cls._number(weight.weight_lb)} lb · {weight.measured_at.date()}"

    @classmethod
    def _bmi(cls, detail: PersonDetail) -> str | None:
        anthropometrics = detail.derived_calculations.anthropometrics
        if anthropometrics.bmi is None:
            return None
        category = anthropometrics.bmi_category
        return (
            f"{cls._number(anthropometrics.bmi)} · {category}"
            if category
            else cls._number(anthropometrics.bmi)
        )

    @classmethod
    def _current_diet(cls, detail: PersonDetail) -> str | None:
        diet = detail.current_diet
        if diet is None:
            return None
        values = [
            cls._pretty(diet.diet_type),
            (
                f"{cls._pretty(diet.texture)} texture"
                if diet.texture is not None
                else None
            ),
            cls._pretty(diet.liquid_consistency),
        ]
        if diet.restrictions:
            values.append(f"restrictions: {', '.join(diet.restrictions)}")
        return ", ".join(value for value in values if value) or "Active diet order"

    @classmethod
    def _nutrition_support(cls, detail: PersonDetail) -> str | None:
        support: list[str] = []
        if detail.current_enteral_feeding is not None:
            feeding = detail.current_enteral_feeding
            support.append(
                "Enteral" + (f": {feeding.formula}" if feeding.formula else " feeding"),
            )
        if detail.current_parenteral_nutrition is not None:
            prescription = detail.current_parenteral_nutrition
            formula_type = cls._pretty(prescription.formula_type)
            support.append(
                "Parenteral nutrition" + (f": {formula_type}" if formula_type else ""),
            )
        return "; ".join(support) or None

    @classmethod
    def _allergies(cls, detail: PersonDetail) -> str | None:
        if any(allergy.no_known_allergies for allergy in detail.active_allergies):
            return "No known allergies documented"
        return cls._preview(
            allergy.allergen for allergy in detail.active_allergies if allergy.allergen
        )

    @staticmethod
    def _number(value: float) -> str:
        return f"{value:g}"

    @staticmethod
    def _pretty(value: object | None) -> str | None:
        if value is None:
            return None
        raw = str(getattr(value, "value", value)).strip()
        return raw.replace("_", " ") if raw else None

    @staticmethod
    def _preview(values: Iterable[str | None], limit: int = 3) -> str | None:
        unique = list(dict.fromkeys(value.strip() for value in values if value))
        if not unique:
            return None
        visible = unique[:limit]
        remainder = len(unique) - len(visible)
        suffix = f" +{remainder} more" if remainder else ""
        return ", ".join(visible) + suffix


__all__ = ["PersonSummaryService"]
