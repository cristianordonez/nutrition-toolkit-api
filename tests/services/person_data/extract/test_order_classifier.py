"""Deterministic classification tests for structured order rows."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ntk.models.extracted_fact_create import (
    DietPayload,
    EnteralFeedingPayload,
    FluidPlanPayload,
    MedicationPayload,
    MiscOrderPayload,
    SupplementPayload,
)
from ntk.models.sql.clinical import ClinicalStatus, FeedingMethod
from ntk.models.sql.food import LiquidConsistency
from ntk.pipelines.person.ingestion.extract.order_classifier import (
    ClassifiedOrderPayload,
    OrderClassifier,
)

_OBSERVED_AT = datetime(2026, 9, 1, tzinfo=UTC)


def _classify(summary: str, category: str) -> ClassifiedOrderPayload:
    return OrderClassifier.classify(
        summary,
        category=category,
        status="Active",
        observed_at=_OBSERVED_AT,
        revision_date=None,
    )


def test_classifies_and_parses_medication() -> None:
    payload = _classify("Lasix 40 mg PO BID", "Pharmacy")

    assert isinstance(payload, MedicationPayload)
    assert payload.name == "Lasix"
    assert payload.dose == 40  # noqa: PLR2004
    assert payload.dose_unit == "mg"
    assert payload.route == "PO"
    assert payload.frequency == "BID"
    assert payload.status is ClinicalStatus.ACTIVE


def test_classifies_and_parses_continuous_enteral_feeding() -> None:
    payload = _classify(
        "Jevity 1.5 @ 80 mL/hr x16 hr with 250 mL FWF q6h",
        "Enteral Feed",
    )

    assert isinstance(payload, EnteralFeedingPayload)
    assert payload.formula == "Jevity 1.5"
    assert payload.feeding_method is FeedingMethod.CONTINUOUS
    assert payload.rate_ml_hr == 80  # noqa: PLR2004
    assert payload.hours_per_day == 16  # noqa: PLR2004
    assert payload.flush_ml == 250  # noqa: PLR2004
    assert payload.flush_frequency_hours == 6  # noqa: PLR2004
    assert payload.caloric_density_kcal_ml == 1.5  # noqa: PLR2004


def test_parses_pcc_cyclic_enteral_feeding_category() -> None:
    payload = _classify(
        "Enteral Feed Order one time a day Provide Nepro 1.8 @ 65 ml/hr "
        "via peg up at 4:00 pm and down until TV of 1100ml infused providing "
        "1947 kcal (32 kcal/kg), 89 g protein (1.4 g/kg) and 800 mL fluids",
        "Enteral - Feed",
    )

    assert isinstance(payload, EnteralFeedingPayload)
    assert payload.formula == "Nepro 1.8"
    assert payload.route == "PEG"
    assert payload.feeding_method is FeedingMethod.CYCLIC
    assert payload.rate_ml_hr == 65  # noqa: PLR2004
    assert payload.hours_per_day == 16.92  # noqa: PLR2004
    assert payload.feeding_schedule == (
        "up at 4:00 pm and down until TV of 1100ml infused"
    )
    assert payload.caloric_density_kcal_ml == 1.8  # noqa: PLR2004


def test_enteral_category_separates_flush_and_ancillary_orders() -> None:
    flush = _classify(
        "Enteral Feed Order one time a day Provide Free Water Flush @ 45 ml/hr "
        "for TV 700 mls",
        "Enteral - Feed",
    )
    head_of_bed = _classify(
        "Enteral Feed Order every shift Elevate head of bed 30-45 degrees "
        "during feeding",
        "Enteral - Feed",
    )

    assert isinstance(flush, FluidPlanPayload)
    assert flush.target_ml_day == 700  # noqa: PLR2004
    assert isinstance(head_of_bed, MiscOrderPayload)


def test_classifies_diet_components_separately() -> None:
    payload = _classify("CCD / Ground / Thin", "Dietary - Diet")

    assert isinstance(payload, DietPayload)
    assert payload.diet_type == "ccd"
    assert payload.texture == "ground"
    assert payload.liquid_consistency is LiquidConsistency.THIN


def test_classifies_npo_as_the_diet_type() -> None:
    payload = _classify(
        "NPO diet NPO texture, NPO consistency, Once completed send a diet "
        "ticket to the kitchen for diet orders",
        "Dietary - Diet",
    )

    assert isinstance(payload, DietPayload)
    assert payload.diet_type == "npo"
    assert payload.texture is None
    assert payload.liquid_consistency is None
    assert payload.restrictions == ["nothing_by_mouth"]


def test_cardiac_rehab_order_is_not_classified_as_a_diet() -> None:
    payload = _classify("Cardiac Rehab Evaluation as needed", "Other")

    assert isinstance(payload, MiscOrderPayload)
    assert payload.description == "Cardiac Rehab Evaluation as needed"
    assert payload.order_type == "Other"


@pytest.mark.parametrize(
    ("summary", "category"),
    [
        (
            "Lipid profile one time only related to end stage renal disease",
            "Laboratory",
        ),
        ("Schedule cardiology visit for cardiac stent follow up", "Other"),
        ("If resident is unconscious or NPO, give glucagon", "Other"),
    ],
)
def test_diet_words_outside_diet_category_are_not_diet_orders(
    summary: str,
    category: str,
) -> None:
    payload = _classify(summary, category)

    assert isinstance(payload, MiscOrderPayload)


def test_classifies_oral_supplement_from_order_context() -> None:
    payload = _classify("Ensure Plus BID", "Dietary - Supplements")

    assert isinstance(payload, SupplementPayload)
    assert payload.product_name == "Ensure Plus"
    assert payload.frequency == "BID"


def test_parses_natural_language_supplement_dose_and_schedule() -> None:
    payload = _classify(
        "Glucerna PO 8 OZ two times a day for malnutrition",
        "Dietary - Supplements",
    )

    assert isinstance(payload, SupplementPayload)
    assert payload.product_name == "Glucerna"
    assert payload.amount == 8  # noqa: PLR2004
    assert payload.unit == "oz"
    assert payload.frequency == "BID"
    assert payload.route == "PO"


def test_uses_primary_supplement_frequency_before_trailing_instruction() -> None:
    payload = _classify(
        "Glucerna PO 8 OZ three times a day for malnutrition "
        "Give 237 ml BID via PO Record % consumed.",
        "Dietary - Supplements",
    )

    assert isinstance(payload, SupplementPayload)
    assert payload.product_name == "Glucerna"
    assert payload.amount == 8  # noqa: PLR2004
    assert payload.unit == "oz"
    assert payload.frequency == "TID"
    assert payload.route == "PO"


def test_parses_spelled_out_supplement_unit() -> None:
    payload = _classify(
        "Magic Cup PO 4 ounces two times a day for malnutrition risk",
        "Dietary - Supplements",
    )

    assert isinstance(payload, SupplementPayload)
    assert payload.product_name == "Magic Cup"
    assert payload.amount == 4  # noqa: PLR2004
    assert payload.unit == "oz"
    assert payload.frequency == "BID"
    assert payload.route == "PO"


def test_parses_natural_language_medication_route_and_frequency() -> None:
    payload = _classify(
        "Acetaminophen Tablet 325 MG Give 2 tablets by mouth "
        "every 6 hours as needed for mild pain. Give 2 tabs = 650MG.",
        "Pharmacy",
    )

    assert isinstance(payload, MedicationPayload)
    assert payload.name == "Acetaminophen Tablet"
    assert payload.dose == 650  # noqa: PLR2004
    assert payload.dose_unit == "mg"
    assert payload.route == "PO"
    assert payload.frequency == "Q6H PRN"
    assert payload.indication == "mild pain"


def test_parses_topical_medication_concentration_and_frequency() -> None:
    payload = _classify(
        "Triamcinolone Acetonide External Cream 0.5 % "
        "Apply to skin topically two times a day for contact dermatitis",
        "Pharmacy",
    )

    assert isinstance(payload, MedicationPayload)
    assert payload.name == "Triamcinolone Acetonide External Cream"
    assert payload.dose == 0.5  # noqa: PLR2004
    assert payload.dose_unit == "%"
    assert payload.route == "TOPICAL"
    assert payload.frequency == "BID"
    assert payload.indication == "contact dermatitis"


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        ("Fluid restriction 1500 mL per day", 1500.0),
        ("Restrict fluids to 1.5 L daily", 1500.0),
        ("FR: 1200 cc/24 hours", 1200.0),
    ],
)
def test_classifies_fluid_restriction(
    summary: str,
    expected: float,
) -> None:
    payload = _classify(summary, "Other")

    assert isinstance(payload, FluidPlanPayload)
    assert payload.restriction_ml_day == expected
    assert payload.target_ml_day is None


def test_classifies_fluid_target() -> None:
    payload = _classify("Encourage oral fluids 1800 mL daily", "Other")

    assert isinstance(payload, FluidPlanPayload)
    assert payload.target_ml_day == 1800  # noqa: PLR2004
    assert payload.restriction_ml_day is None


def test_combined_diet_and_fluid_order_produces_both_facts() -> None:
    payloads = OrderClassifier.classify_many(
        "Regular diet, thin liquids, 1500 mL fluid restriction",
        category="Dietary - Diet",
        status="Active",
        observed_at=_OBSERVED_AT,
        revision_date=None,
    )

    assert len(payloads) == 2  # noqa: PLR2004
    assert isinstance(payloads[0], DietPayload)
    assert payloads[0].diet_type == "regular"
    assert isinstance(payloads[1], FluidPlanPayload)
    assert payloads[1].restriction_ml_day == 1500  # noqa: PLR2004


@pytest.mark.parametrize("category", ["Nursing", "Laboratory"])
def test_unrecognized_legitimate_order_uses_misc_fallback(category: str) -> None:
    payload = _classify("Weekly skin assessment", category)

    assert isinstance(payload, MiscOrderPayload)
    assert payload.description == "Weekly skin assessment"
    assert payload.order_type == category
