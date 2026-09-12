"""Deterministically classify and parse rows from structured order reports."""

from __future__ import annotations

import re
from datetime import date, datetime  # noqa: TC003

from ntk.models.extracted_fact_create import (
    DietPayload,
    EnteralFeedingPayload,
    FluidPlanPayload,
    MedicationPayload,
    MiscOrderPayload,
    ParenteralAccessRoute,
    ParenteralNutritionPayload,
    SupplementPayload,
)
from ntk.models.sql.clinical import ClinicalStatus, FeedingMethod
from ntk.models.sql.clinical.common import LipidDeliveryType, ParenteralFormulaType
from ntk.models.sql.food import LiquidConsistency

ClassifiedOrderPayload = (
    MedicationPayload
    | EnteralFeedingPayload
    | DietPayload
    | SupplementPayload
    | FluidPlanPayload
    | ParenteralNutritionPayload
    | MiscOrderPayload
)


_DOSE_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<dose>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>mcg|mg|g|ml|meq|units?|iu|%)"
    r"(?=\s|$|\()",
    flags=re.IGNORECASE,
)
_EXPLICIT_ADMIN_DOSE_RE = re.compile(
    r"=\s*(?P<dose>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>mcg|mg|g|ml|meq|units?|iu|%)"
    r"(?=\s|[.,;]|$)",
    flags=re.IGNORECASE,
)
_ROUTE_RE = re.compile(
    r"\b(?P<route>PO|PEG|GT|G[- ]?TUBE|NG|NJ|J[- ]?TUBE|IV|IM|SQ|SC|SL|PR|"
    r"BY\s+MOUTH|ORALLY|RECTALLY|TOPICALLY|SUBCUTANEOUSLY)\b",
    flags=re.IGNORECASE,
)
_INTERVAL_FREQUENCY_RE = re.compile(
    r"\b(?:Q\s*(?P<q_hours>\d+(?:\.\d+)?)\s*H(?:RS?)?|"
    r"EVERY\s+(?P<every_hours>\d+(?:\.\d+)?)\s*(?:H|HR|HOUR)S?)\b",
    flags=re.IGNORECASE,
)
_PRN_RE = re.compile(r"\b(?:PRN|AS\s+NEEDED)\b", flags=re.IGNORECASE)
_FREQUENCY_PATTERNS = (
    (
        re.compile(
            r"\b(?:BID|TWICE\s+(?:DAILY|A\s+DAY)|"
            r"TWO\s+TIMES\s+(?:DAILY|A\s+DAY))\b",
            flags=re.IGNORECASE,
        ),
        "BID",
    ),
    (
        re.compile(
            r"\b(?:TID|THREE\s+TIMES\s+(?:DAILY|A\s+DAY))\b",
            flags=re.IGNORECASE,
        ),
        "TID",
    ),
    (
        re.compile(
            r"\b(?:QID|FOUR\s+TIMES\s+(?:DAILY|A\s+DAY))\b",
            flags=re.IGNORECASE,
        ),
        "QID",
    ),
    (re.compile(r"\bQHS\b", flags=re.IGNORECASE), "QHS"),
    (re.compile(r"\bQAM\b", flags=re.IGNORECASE), "QAM"),
    (re.compile(r"\bQPM\b", flags=re.IGNORECASE), "QPM"),
    (
        re.compile(
            r"\b(?:QD|DAILY|ONCE\s+DAILY|ONCE\s+A\s+DAY|"
            r"ONE\s+TIME\s+(?:DAILY|A\s+DAY)|EVERY\s+DAY(?:\s+SHIFT)?)\b",
            flags=re.IGNORECASE,
        ),
        "DAILY",
    ),
    (
        re.compile(r"\b(?:WITH\s+MEALS|WITH\s+EACH\s+MEAL)\b", re.IGNORECASE),
        "WITH MEALS",
    ),
    (
        re.compile(r"\b(?:Q\s*SHIFT|EVERY\s+SHIFT)\b", re.IGNORECASE),
        "EVERY SHIFT",
    ),
)
_RATE_RE = re.compile(
    r"(?:@|at)\s*(?P<rate>\d+(?:\.\d+)?)\s*m[lL]\s*/?\s*(?:hr|hour)",
    flags=re.IGNORECASE,
)
_HOURS_RE = re.compile(
    r"(?:x|for|over)\s*(?P<hours>\d+(?:\.\d+)?)\s*(?:hr|hour)s?",
    flags=re.IGNORECASE,
)
_BOLUS_RE = re.compile(
    r"(?P<volume>\d+(?:\.\d+)?)\s*m[lL]\s+(?:bolus\s+)?"
    r"(?P<count>\d+)\s*(?:times?|x)\s*(?:daily|per\s+day)",
    flags=re.IGNORECASE,
)
_FLUSH_RE = re.compile(
    r"(?P<volume>\d+(?:\.\d+)?)\s*m[lL]\s+"
    r"(?:free\s+water\s+|water\s+)?(?:flush(?:es)?|FWF)\s*"
    r"(?:every|q)\s*(?P<hours>\d+(?:\.\d+)?)\s*(?:h|hr|hour)s?",
    flags=re.IGNORECASE,
)
_FLUSH_ONLY_RE = re.compile(
    r"(?:free\s+water\s+|water\s+)?(?:flush(?:es)?|FWF)",
    flags=re.IGNORECASE,
)
_FORMULA_RE = re.compile(
    r"^(?P<formula>.+?)\s*(?:@|at)\s*\d+(?:\.\d+)?\s*m[lL]",
    flags=re.IGNORECASE,
)
_ENTERAL_ORDER_PREFIX_RE = re.compile(
    r"^(?:enteral\s+feed(?:ing)?(?:\s+order)?|tube\s*feed(?:ing)?|TF)\s*[:\-]?\s*",
    flags=re.IGNORECASE,
)
_ENTERAL_SCHEDULE_PREFIX_RE = re.compile(
    r"^(?:(?:one|1)\s+time\s+a\s+day|once\s+daily|daily)\s+",
    flags=re.IGNORECASE,
)
_PROVIDE_PREFIX_RE = re.compile(r"^provide\s+", flags=re.IGNORECASE)
_TOTAL_VOLUME_RE = re.compile(
    r"\b(?:TV|total\s+volume)(?:\s+of)?\s*(?P<amount>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>m[lL]s?)\b",
    flags=re.IGNORECASE,
)
_FEEDING_SCHEDULE_RE = re.compile(
    r"\bup\s+at\s+.+?\bdown\s+until\s+.+?(?=\s+providing\b|$)",
    flags=re.IGNORECASE,
)
_ENTERAL_ANCILLARY_RE = re.compile(
    r"\b(?:document\s+TV\s+infused|elevate\s+head\s+of\s+bed|"
    r"flush\s+(?:GT|G[- ]?tube).+?medications?)\b",
    flags=re.IGNORECASE,
)
_DENSITY_RE = re.compile(r"\b(?P<density>[1-2](?:\.\d+)?)\b")
_AMOUNT_RE = re.compile(
    r"\b(?P<amount>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>fl\s*oz|oz|ounces?|ml|milliliters?|packets?|cups?)\b",
    flags=re.IGNORECASE,
)
_FLUID_PLAN_TERMS = re.compile(
    r"\b(?:"
    r"fluid\s+restriction|"
    r"restrict(?:ed)?\s+(?:oral\s+)?fluids?|"
    r"fluids?\s+restricted|"
    r"fluid\s+(?:goal|target)|"
    r"encourage\s+(?:oral\s+)?fluids?|"
    r"FR\s*[:\-]?\s*\d+(?:\.\d+)?"
    r")\b",
    flags=re.IGNORECASE,
)
_FLUID_VOLUME_RE = re.compile(
    r"\b(?P<amount>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>ml|milliliters?|cc|l|liters?)\b",
    flags=re.IGNORECASE,
)
_FLUID_TARGET_TERMS = re.compile(
    r"\b(?:"
    r"fluid\s+(?:goal|target)|"
    r"encourage\s+(?:oral\s+)?fluids?"
    r")\b",
    flags=re.IGNORECASE,
)
_INDICATION_RE = re.compile(
    r"\bfor\s+(?P<indication>.+?)(?=\s+(?:give|apply|insert|record)\b|$)",
    flags=re.IGNORECASE,
)
_ENTERAL_TERMS = re.compile(
    r"\b(?:tube\s*feed|enteral|PEG|G[- ]?tube|NG|NJ|J[- ]?tube|FWF|flush)\b",
    flags=re.IGNORECASE,
)
_DIET_TERMS = re.compile(
    r"\b(?:NPO|nothing\s+by\s+mouth|regular|CCD|cardiac|NAS|renal|"
    r"puree(?:d)?|ground|mechanical\s+soft|"
    r"soft\s*(?:&|and)\s*bite[- ]sized|thin\s+liquids?|nectar[- ]thick|"
    r"honey[- ]thick|2\s*g(?:m)?\s+Na|low\s+fat|low\s+cholesterol)\b",
    flags=re.IGNORECASE,
)
_SUPPLEMENT_TERMS = re.compile(
    r"\b(?:ensure(?:\s+plus|\s+clear)?|glucerna|nepro|"
    r"(?:sugar[- ]free\s+)?health\s*shake|"
    r"magic\s+cup|prostat|resource\s+2\.0|super\s+cereal)\b",
    flags=re.IGNORECASE,
)
_HOURS_PER_DAY = 24
_PARENTERAL_NUTRITION_TERMS = re.compile(
    r"\b(?:TPN|PPN|"
    r"total\s+parenteral\s+nutrition|"
    r"peripheral\s+parenteral\s+nutrition|"
    r"parenteral\s+nutrition)\b",
    flags=re.IGNORECASE,
)
_PN_TOTAL_VOLUME_RE = re.compile(
    r"\b(?:total\s+volume|TV)\s*(?:[:=]|of)?\s*"
    r"(?P<volume>\d+(?:\.\d+)?)\s*mL\b",
    flags=re.IGNORECASE,
)
_PN_RATE_RE = re.compile(
    r"\b(?:TPN|PPN|parenteral\s+nutrition).*?"
    r"(?:@|at)\s*(?P<rate>\d+(?:\.\d+)?)\s*mL\s*/?\s*(?:hr|hour)",
    flags=re.IGNORECASE,
)
_PN_HOURS_RE = re.compile(
    r"\b(?:over|for|x)\s*(?P<hours>\d+(?:\.\d+)?)\s*(?:hr|hour)s?\b",
    flags=re.IGNORECASE,
)
_PN_DEXTROSE_RE = re.compile(
    r"\b(?:dextrose|dex)\s*"
    r"(?P<grams>\d+(?:\.\d+)?)\s*g\s*/\s*l\b",
    flags=re.IGNORECASE,
)
_PN_AMINO_ACID_RE = re.compile(
    r"\b(?:amino\s+acids?|AA)\s*"
    r"(?P<grams>\d+(?:\.\d+)?)\s*g\s*/\s*l\b",
    flags=re.IGNORECASE,
)
_PN_PROTEIN_RE = re.compile(
    r"\bprotein\s*(?P<grams>\d+(?:\.\d+)?)\s*g\b",
    flags=re.IGNORECASE,
)
_PN_CALORIES_RE = re.compile(
    r"\b(?P<kcal>\d+(?:\.\d+)?)\s*kcal\b",
    flags=re.IGNORECASE,
)
_PN_LIPID_CONCENTRATION_RE = re.compile(
    r"\b(?:lipid|IVFE|intralipid)\s*(?P<percent>\d+(?:\.\d+)?)\s*%",
    flags=re.IGNORECASE,
)
_PN_LIPID_VOLUME_RE = re.compile(
    r"\b(?:lipid|IVFE|intralipid).*?"
    r"(?P<volume>\d+(?:\.\d+)?)\s*mL\b",
    flags=re.IGNORECASE,
)
_PN_LIPID_RATE_RE = re.compile(
    r"\b(?:lipid|IVFE|intralipid).*?"
    r"(?:@|at)\s*(?P<rate>\d+(?:\.\d+)?)\s*mL\s*/?\s*(?:hr|hour)",
    flags=re.IGNORECASE,
)
_PN_LIPID_HOURS_RE = re.compile(
    r"\b(?:lipid|IVFE|intralipid).*?"
    r"(?:over|for|x)\s*(?P<hours>\d+(?:\.\d+)?)\s*(?:hr|hour)s?\b",
    flags=re.IGNORECASE,
)
_PN_ACCESS_DESCRIPTION_RE = re.compile(
    r"\b(?P<access>"
    r"PICC|CVC|central venous catheter|central line|"
    r"peripheral IV|peripheral line"
    r")\b",
    flags=re.IGNORECASE,
)


class OrderClassifier:
    """Classify one recognized order-report row without using an LLM."""

    @classmethod
    def classify_many(
        cls,
        summary: str,
        *,
        category: str | None,
        status: str | None,
        observed_at: datetime | None,
        revision_date: date | None,
    ) -> list[ClassifiedOrderPayload]:
        """Return every supported fact represented by one source order."""
        primary = cls.classify(
            summary,
            category=category,
            status=status,
            observed_at=observed_at,
            revision_date=revision_date,
        )
        payloads = [primary]
        if _FLUID_PLAN_TERMS.search(summary) and not isinstance(
            primary,
            FluidPlanPayload,
        ):
            payloads.append(
                cls._fluid_plan(
                    summary,
                    status=cls._status(status),
                    observed_at=observed_at,
                    instructions=summary,
                    source_category=category,
                    source_revision_date=revision_date,
                ),
            )
        return payloads

    @classmethod
    def classify(  # noqa: C901, PLR0911
        cls,
        summary: str,
        *,
        category: str | None,
        status: str | None,
        observed_at: datetime | None,
        revision_date: date | None,
    ) -> ClassifiedOrderPayload:
        """Return the semantic payload supported by category and order text."""
        normalized_category = cls._normalize(category)
        normalized_status = cls._status(status)
        common = {
            "status": normalized_status,
            "observed_at": observed_at,
            "instructions": summary,
            "source_category": category,
            "source_revision_date": revision_date,
        }

        if _PARENTERAL_NUTRITION_TERMS.search(summary):
            return cls._parenteral_nutrition(summary, **common)
        if normalized_category == "pharmacy":
            return cls._medication(summary, **common)
        if normalized_category in {"enteral feed", "enteral - feed"}:
            if cls._is_flush_only_order(summary):
                return cls._fluid_plan(summary, **common)
            if _ENTERAL_ANCILLARY_RE.search(summary):
                return MiscOrderPayload.model_validate(
                    {
                        "order_type": category,
                        "description": summary,
                        **common,
                    },
                )

            return cls._enteral_feeding(summary, **common)
        if normalized_category == "dietary - diet":
            if _FLUID_PLAN_TERMS.search(summary) and not _DIET_TERMS.search(summary):
                return cls._fluid_plan(summary, **common)
            return cls._diet(summary, **common)
        if normalized_category == "dietary - supplements":
            return cls._supplement(summary, **common)
        if _FLUID_PLAN_TERMS.search(summary):
            return cls._fluid_plan(summary, **common)
        if _ENTERAL_TERMS.search(summary):
            return cls._enteral_feeding(summary, **common)
        if _SUPPLEMENT_TERMS.search(summary):
            return cls._supplement(summary, **common)
        return MiscOrderPayload.model_validate(
            {
                "order_type": category,
                "description": summary,
                **common,
            },
        )

    @classmethod
    def _parenteral_nutrition(
        cls,
        summary: str,
        **common: object,
    ) -> ParenteralNutritionPayload:
        normalized = summary.casefold()
        total_volume_match = _PN_TOTAL_VOLUME_RE.search(summary)
        rate_match = _PN_RATE_RE.search(summary)
        hours_match = _PN_HOURS_RE.search(summary)
        dextrose_match = _PN_DEXTROSE_RE.search(summary)
        amino_match = _PN_AMINO_ACID_RE.search(summary)
        protein_match = _PN_PROTEIN_RE.search(summary)
        calories_match = _PN_CALORIES_RE.search(summary)
        lipid_concentration_match = _PN_LIPID_CONCENTRATION_RE.search(summary)
        lipid_volume_match = _PN_LIPID_VOLUME_RE.search(summary)
        lipid_rate_match = _PN_LIPID_RATE_RE.search(summary)
        lipid_hours_match = _PN_LIPID_HOURS_RE.search(summary)
        access_route = None
        access_description = None
        access_match = _PN_ACCESS_DESCRIPTION_RE.search(summary)
        access_description = (
            access_match.group("access").strip() if access_match else None
        )

        if "ppn" in normalized or "peripheral parenteral nutrition" in normalized:
            access_route = ParenteralAccessRoute.PERIPHERAL
        elif (
            "tpn" in normalized
            or "total parenteral nutrition" in normalized
            or any(
                term in normalized
                for term in (
                    "central venous",
                    "central line",
                    "picc",
                    "cvc",
                )
            )
        ):
            access_route = ParenteralAccessRoute.CENTRAL
        formula_type = None
        if "concentrated" in normalized:
            formula_type = ParenteralFormulaType.CONCENTRATED
        elif "standard" in normalized:
            formula_type = ParenteralFormulaType.STANDARD
        lipid_delivery = None
        if "piggyback" in normalized:
            lipid_delivery = LipidDeliveryType.PIGGYBACK
        elif any(
            term in normalized
            for term in ("3-in-1", "3 in 1", "total nutrient admixture")
        ):
            lipid_delivery = LipidDeliveryType.INCLUDED
        return ParenteralNutritionPayload.model_validate(
            {
                "access_route": access_route,
                "access_description": access_description,
                "formula_type": formula_type,
                "total_volume_ml": (
                    float(total_volume_match.group("volume"))
                    if total_volume_match
                    else None
                ),
                "rate_ml_hr": (float(rate_match.group("rate")) if rate_match else None),
                "hours_per_day": (
                    float(hours_match.group("hours")) if hours_match else None
                ),
                "dextrose_g_per_l": (
                    float(dextrose_match.group("grams")) if dextrose_match else None
                ),
                "amino_acid_g_per_l": (
                    float(amino_match.group("grams")) if amino_match else None
                ),
                "documented_protein_g": (
                    float(protein_match.group("grams")) if protein_match else None
                ),
                "documented_calories_kcal": (
                    float(calories_match.group("kcal")) if calories_match else None
                ),
                "lipid_delivery": lipid_delivery,
                "lipid_concentration_percent": (
                    float(lipid_concentration_match.group("percent"))
                    if lipid_concentration_match
                    else None
                ),
                "lipid_total_volume_ml": (
                    float(lipid_volume_match.group("volume"))
                    if lipid_volume_match
                    else None
                ),
                "lipid_run_time_hours": (
                    float(lipid_hours_match.group("hours"))
                    if lipid_hours_match
                    else None
                ),
                "lipid_rate_ml_hr": (
                    float(lipid_rate_match.group("rate")) if lipid_rate_match else None
                ),
                **common,
            },
        )

    @classmethod
    def _medication(cls, summary: str, **common: object) -> MedicationPayload:
        strength_match = _DOSE_RE.search(summary)
        administered_dose_match = _EXPLICIT_ADMIN_DOSE_RE.search(summary)
        dose_match = administered_dose_match or strength_match
        name = (
            strength_match.group("name").strip() if strength_match else summary.strip()
        )
        indication_match = _INDICATION_RE.search(summary)
        return MedicationPayload.model_validate(
            {
                "name": name,
                "dose": float(dose_match.group("dose")) if dose_match else None,
                "dose_text": dose_match.group("dose") if dose_match else None,
                "dose_unit": (
                    cls._medication_unit(dose_match.group("unit"))
                    if dose_match
                    else None
                ),
                "route": cls._route(summary),
                "frequency": cls._frequency(summary),
                "indication": (
                    indication_match.group("indication").strip(" .,;")
                    if indication_match
                    else None
                ),
                **common,
            },
        )

    @classmethod
    def _enteral_feeding(
        cls,
        summary: str,
        **common: object,
    ) -> EnteralFeedingPayload:
        formula_match = _FORMULA_RE.search(summary)
        rate_match = _RATE_RE.search(summary)
        hours_match = _HOURS_RE.search(summary)
        bolus_match = _BOLUS_RE.search(summary)
        flush_match = _FLUSH_RE.search(summary)
        total_volume_match = _TOTAL_VOLUME_RE.search(summary)
        schedule_match = _FEEDING_SCHEDULE_RE.search(summary)
        formula = formula_match.group("formula").strip() if formula_match else None
        if formula is not None:
            formula = _ENTERAL_ORDER_PREFIX_RE.sub("", formula)
            formula = _ENTERAL_SCHEDULE_PREFIX_RE.sub("", formula)
            formula = _PROVIDE_PREFIX_RE.sub("", formula)
        density_match = _DENSITY_RE.search(formula or "")
        if bolus_match:
            method = FeedingMethod.BOLUS
        elif re.search(
            r"\bcyclic\b|\bup\s+at\s+.+?\bdown\s+until\b",
            summary,
            flags=re.IGNORECASE,
        ):
            method = FeedingMethod.CYCLIC
        elif rate_match:
            method = FeedingMethod.CONTINUOUS
        else:
            method = FeedingMethod.UNKNOWN
        hours_per_day = float(hours_match.group("hours")) if hours_match else None
        if hours_per_day is None and rate_match and total_volume_match:
            rate = float(rate_match.group("rate"))
            calculated_hours = float(total_volume_match.group("amount")) / rate
            if calculated_hours <= _HOURS_PER_DAY:
                hours_per_day = round(calculated_hours, 2)
        return EnteralFeedingPayload.model_validate(
            {
                "formula": formula,
                "route": cls._route(summary),
                "feeding_method": method,
                "rate_ml_hr": float(rate_match.group("rate")) if rate_match else None,
                "hours_per_day": hours_per_day,
                "bolus_volume_ml": (
                    float(bolus_match.group("volume")) if bolus_match else None
                ),
                "boluses_per_day": (
                    int(bolus_match.group("count")) if bolus_match else None
                ),
                "flush_ml": (
                    float(flush_match.group("volume")) if flush_match else None
                ),
                "flush_frequency_hours": (
                    float(flush_match.group("hours")) if flush_match else None
                ),
                "flush_instructions": flush_match.group(0) if flush_match else None,
                "feeding_schedule": (
                    schedule_match.group(0).strip() if schedule_match else None
                ),
                "caloric_density_kcal_ml": (
                    float(density_match.group("density")) if density_match else None
                ),
                **common,
            },
        )

    @classmethod
    def _diet(cls, summary: str, **common: object) -> DietPayload:
        normalized = cls._normalize(summary)
        is_npo = bool(
            re.search(r"\b(?:npo|nothing\s+by\s+mouth)\b", normalized),
        )
        texture = next(
            (
                value
                for term, value in (
                    ("pureed", "pureed"),
                    ("puree", "pureed"),
                    ("ground", "ground"),
                    ("mechanical soft", "mechanical_soft"),
                    ("soft & bite-sized", "soft_and_bite_sized"),
                    ("soft and bite-sized", "soft_and_bite_sized"),
                )
                if term in normalized
            ),
            None,
        )
        liquid = next(
            (
                value
                for term, value in (
                    ("thin", LiquidConsistency.THIN),
                    ("nectar", LiquidConsistency.MILDLY_THICK),
                    ("honey", LiquidConsistency.MODERATELY_THICK),
                )
                if term in normalized
            ),
            None,
        )
        diet_type = (
            "npo"
            if is_npo
            else next(
                (
                    value
                    for term, value in (
                        ("regular", "regular"),
                        ("ccd", "ccd"),
                        ("cardiac", "cardiac"),
                        ("renal", "renal"),
                        ("nas", "nas"),
                    )
                    if re.search(rf"\b{re.escape(term)}\b", normalized)
                ),
                None,
            )
        )
        restrictions = [
            value
            for term, value in (
                ("2 gm na", "2_g_sodium"),
                ("2 g na", "2_g_sodium"),
                ("low fat", "low_fat"),
                ("low cholesterol", "low_cholesterol"),
            )
            if term in normalized
        ]
        if is_npo:
            restrictions.append("nothing_by_mouth")
        return DietPayload.model_validate(
            {
                "diet_type": diet_type,
                "texture": texture,
                "liquid_consistency": liquid,
                "restrictions": sorted(set(restrictions)),
                **common,
            },
        )

    @classmethod
    def _supplement(cls, summary: str, **common: object) -> SupplementPayload:
        product_match = _SUPPLEMENT_TERMS.search(summary)
        amount_match = _AMOUNT_RE.search(summary)
        return SupplementPayload.model_validate(
            {
                "product_name": (
                    product_match.group(0).strip()
                    if product_match
                    else cls._supplement_name(summary)
                ),
                "amount": (
                    float(amount_match.group("amount")) if amount_match else None
                ),
                "unit": (
                    cls._supplement_unit(amount_match.group("unit"))
                    if amount_match
                    else None
                ),
                "frequency": cls._frequency(summary),
                "route": cls._route(summary),
                **common,
            },
        )

    @staticmethod
    def _fluid_plan(summary: str, **common: object) -> FluidPlanPayload:
        volume_match = _TOTAL_VOLUME_RE.search(summary) or _FLUID_VOLUME_RE.search(
            summary,
        )
        volume_ml: float | None = None
        if volume_match:
            volume_ml = float(volume_match.group("amount"))
            if volume_match.group("unit").casefold() in {"l", "liter", "liters"}:
                volume_ml *= 1000
        has_target_terms = _FLUID_TARGET_TERMS.search(summary) is not None
        is_target = has_target_terms or OrderClassifier._is_flush_only_order(summary)
        return FluidPlanPayload.model_validate(
            {
                "target_ml_day": volume_ml if is_target else None,
                "restriction_ml_day": volume_ml if not is_target else None,
                **common,
            },
        )

    @staticmethod
    def _is_flush_only_order(summary: str) -> bool:
        """Return whether an enteral-category row contains only a water flush."""
        formula_match = _FORMULA_RE.search(summary)
        if formula_match is None:
            return False
        candidate = formula_match.group("formula").strip()
        candidate = _ENTERAL_ORDER_PREFIX_RE.sub("", candidate)
        candidate = _ENTERAL_SCHEDULE_PREFIX_RE.sub("", candidate)
        candidate = _PROVIDE_PREFIX_RE.sub("", candidate)
        return _FLUSH_ONLY_RE.fullmatch(candidate.strip()) is not None

    @staticmethod
    def _route(summary: str) -> str | None:
        match = _ROUTE_RE.search(summary)
        if match is None:
            return None
        route = " ".join(match.group("route").upper().split())
        return {
            "BY MOUTH": "PO",
            "ORALLY": "PO",
            "RECTALLY": "PR",
            "TOPICALLY": "TOPICAL",
            "SUBCUTANEOUSLY": "SQ",
            "SC": "SQ",
            "G TUBE": "G-TUBE",
            "GT": "G-TUBE",
            "J TUBE": "J-TUBE",
        }.get(route, route)

    @staticmethod
    def _frequency(summary: str) -> str | None:
        interval_match = _INTERVAL_FREQUENCY_RE.search(summary)
        candidates: list[tuple[int, str]] = []
        if interval_match:
            hours = interval_match.group("q_hours") or interval_match.group(
                "every_hours",
            )
            numeric_hours = float(hours)
            formatted_hours = (
                str(int(numeric_hours))
                if numeric_hours.is_integer()
                else str(numeric_hours)
            )
            candidates.append((interval_match.start(), f"Q{formatted_hours}H"))
        for pattern, canonical in _FREQUENCY_PATTERNS:
            match = pattern.search(summary)
            if match is not None:
                candidates.append((match.start(), canonical))
        frequency = min(candidates, key=lambda item: item[0])[1] if candidates else None
        is_prn = _PRN_RE.search(summary) is not None
        if is_prn and frequency:
            return f"{frequency} PRN"
        if is_prn:
            return "PRN"
        return frequency

    @staticmethod
    def _medication_unit(unit: str) -> str:
        normalized = unit.casefold()
        return {
            "ml": "mL",
            "meq": "mEq",
            "iu": "IU",
        }.get(normalized, normalized)

    @staticmethod
    def _supplement_unit(unit: str) -> str:
        normalized = " ".join(unit.casefold().split())
        if normalized in {"fl oz", "oz", "ounce", "ounces"}:
            return "oz"
        if normalized in {"ml", "milliliter", "milliliters"}:
            return "mL"
        if normalized in {"packet", "packets"}:
            return "packet"
        return "cup"

    @staticmethod
    def _supplement_name(summary: str) -> str:
        marker = re.search(
            r"\s+(?:PO\b|BY\s+MOUTH\b|\d+(?:\.\d+)?\s*"
            r"(?:FL\s*)?(?:OZ|OUNCES?|ML|MILLILITERS?|PACKETS?|CUPS?)\b)",
            summary,
            flags=re.IGNORECASE,
        )
        if marker is None:
            return summary.strip()
        return summary[: marker.start()].strip()

    @staticmethod
    def _normalize(value: str | None) -> str:
        return " ".join((value or "").casefold().split())

    @staticmethod
    def _status(value: str | None) -> ClinicalStatus:
        normalized = " ".join((value or "").casefold().split())
        if normalized == "active":
            return ClinicalStatus.ACTIVE
        if normalized in {"inactive", "discontinued", "completed"}:
            return ClinicalStatus.INACTIVE
        return ClinicalStatus.UNKNOWN


__all__ = ["ClassifiedOrderPayload", "OrderClassifier"]
