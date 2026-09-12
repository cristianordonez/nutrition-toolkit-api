from __future__ import annotations

from dataclasses import dataclass

from ntk.models.sql.food import (
    LiquidConsistency,
    NutrientClassification,
    PackageType,
)

ADMIN_PERMISSION = "admin"
ASSESSMENTS_READ_PERMISSION = "assessments:read"
ASSESSMENTS_WRITE_PERMISSION = "assessments:write"
CALCULATE_READ_PERMISSION = "calculate:read"
KNOWLEDGE_READ_PERMISSION = "knowledge:read"
KNOWLEDGE_WRITE_PERMISSION = "knowledge:write"
PERSONS_READ_PERMISSION = "persons:read"
PERSONS_WRITE_PERMISSION = "persons:write"

DEFAULT_PERMISSIONS = [
    ADMIN_PERMISSION,
    ASSESSMENTS_READ_PERMISSION,
    ASSESSMENTS_WRITE_PERMISSION,
    CALCULATE_READ_PERMISSION,
    KNOWLEDGE_READ_PERMISSION,
    KNOWLEDGE_WRITE_PERMISSION,
    PERSONS_READ_PERMISSION,
    PERSONS_WRITE_PERMISSION,
]


@dataclass(frozen=True, slots=True)
class DefaultNutrientAmount:
    """Nutrient metadata and amount for one built-in food serving."""

    name: str
    number: int
    unit_name: str
    classification: NutrientClassification
    amount: float


@dataclass(frozen=True, slots=True)
class DefaultFormula:
    """Manufacturer formula data seeded into the food tables at startup."""

    name: str
    package_type: PackageType
    brand: str
    serving_size_ml: float
    nutrients: tuple[DefaultNutrientAmount, ...]
    brand_owner: str = "Abbott Nutrition"
    liquid_consistency: LiquidConsistency = LiquidConsistency.MILDLY_THICK

    @property
    def source_id(self) -> str:
        """Return the stable manufacturer identity used for idempotent upserts."""
        return "-".join(self.name.casefold().replace(",", "").split())


@dataclass(frozen=True, slots=True)
class DefaultFacility:
    """Trusted facility metadata seeded into the database at startup."""

    name: str
    facility_identifier: str | None = None
    aliases: tuple[str, ...] = ()


DEFAULT_FACILITIES = (
    DefaultFacility(
        name="Embassy Manor at Edison",
        facility_identifier="embassy-manor-edison",
        aliases=(
            "Embassy Manor",
            "Embassy Manor Edison",
            "Aristacare at Embassy Manor",
        ),
    ),
)


_NUTRIENT_SPECS = (
    ("Energy", 1008, "kcal", NutrientClassification.MACRONUTRIENT),
    ("Protein", 1003, "g", NutrientClassification.MACRONUTRIENT),
    ("Total lipid (fat)", 1004, "g", NutrientClassification.MACRONUTRIENT),
    (
        "Carbohydrate, by difference",
        1005,
        "g",
        NutrientClassification.MACRONUTRIENT,
    ),
    ("Free water", 1051, "mL", NutrientClassification.MACRONUTRIENT),
    ("Fiber, total dietary", 1079, "g", NutrientClassification.MACRONUTRIENT),
    (
        "Sugars, total including NLEA",
        1063,
        "g",
        NutrientClassification.MACRONUTRIENT,
    ),
    ("Sodium, Na", 1093, "mg", NutrientClassification.MINERAL),
    ("Potassium, K", 1092, "mg", NutrientClassification.MINERAL),
    ("Chloride, Cl", 1088, "mg", NutrientClassification.MINERAL),
    ("Calcium, Ca", 1087, "mg", NutrientClassification.MINERAL),
    ("Phosphorus, P", 1091, "mg", NutrientClassification.MINERAL),
)


def _formula(
    name: str,
    package_type: PackageType,
    brand: str,
    serving_size_ml: float,
    amounts: tuple[float, ...],
) -> DefaultFormula:
    """Combine formula-specific amounts with the shared nutrient definitions."""
    nutrients = tuple(
        DefaultNutrientAmount(
            name=nutrient_name,
            number=number,
            unit_name=unit_name,
            classification=classification,
            amount=amount,
        )
        for (nutrient_name, number, unit_name, classification), amount in zip(
            _NUTRIENT_SPECS,
            amounts,
            strict=True,
        )
    )
    return DefaultFormula(
        name=name,
        package_type=package_type,
        brand=brand,
        serving_size_ml=serving_size_ml,
        nutrients=nutrients,
    )


DEFAULT_FORMULAS = (
    _formula(
        "jevity 1.2 1L ready-to-hang",
        PackageType.READY_TO_HANG,
        "Jevity",
        1000,
        (1200, 55.5, 39.3, 169.4, 807, 17, 13, 1067, 2390, 1500, 1200, 1200),
    ),
    _formula(
        "jevity 1.2 1.5L ready-to-hang",
        PackageType.READY_TO_HANG,
        "Jevity",
        1500,
        (1800, 83.3, 59, 254, 1211, 25.5, 20, 1600, 3585, 2250, 1800, 1800),
    ),
    _formula(
        "jevity 1.2 237 mL carton",
        PackageType.CARTON,
        "Jevity",
        237,
        (285, 13.2, 9.3, 40.2, 191, 4, 3, 253, 566, 356, 284, 284),
    ),
    _formula(
        "jevity 1.5, 1L ready-to-hang",
        PackageType.READY_TO_HANG,
        "Jevity",
        1000,
        (1500, 63.8, 49.8, 215.7, 760, 21, 15, 1330, 2180, 1360, 1300, 1250),
    ),
    _formula(
        "jevity 1.5, 1.5L ready-to-hang",
        PackageType.READY_TO_HANG,
        "Jevity",
        1500,
        (2250, 95.7, 74.7, 323.6, 1140, 31.5, 22.5, 1995, 3270, 2040, 1950, 1875),
    ),
    _formula(
        "jevity 1.5, 237 mL carton",
        PackageType.CARTON,
        "Jevity",
        237,
        (355, 15.1, 11.8, 51.1, 180, 5, 3.6, 316, 517, 322, 308, 296),
    ),
    _formula(
        "osmolite 1.5 237 mL carton",
        PackageType.CARTON,
        "Osmolite",
        237,
        (355, 14.9, 11.6, 48.2, 181, 0, 2.5, 316, 517, 403, 308, 296),
    ),
    _formula(
        "osmolite 1.5 1L ready-to-hang",
        PackageType.READY_TO_HANG,
        "Osmolite",
        1000,
        (1500, 62.7, 49.1, 203.6, 762, 0, 10.5, 1330, 2180, 1700, 1300, 1250),
    ),
    _formula(
        "osmolite 1.2 237 mL carton",
        PackageType.CARTON,
        "Osmolite",
        237,
        (285, 13.2, 9.3, 37.5, 195, 0, 2, 253, 539, 356, 284, 284),
    ),
    _formula(
        "osmolite 1.2 1L ready-to-hang",
        PackageType.READY_TO_HANG,
        "Osmolite",
        1000,
        (1200, 55.5, 39.3, 157.5, 820, 0, 8.4, 1067, 2274, 1500, 1200, 1200),
    ),
    _formula(
        "osmolite 1.2 1.5L ready-to-hang",
        PackageType.READY_TO_HANG,
        "Osmolite",
        1500,
        (1800, 83.3, 59, 236.1, 1230, 0, 12.7, 1600, 3410, 2250, 1800, 1800),
    ),
    _formula(
        "nepro 1.8 237 mL carton",
        PackageType.CARTON,
        "Nepro",
        237,
        (420, 19, 23, 38, 172, 6, 8.4, 250, 225, 200, 250, 170),
    ),
    _formula(
        "nepro 1.8 1L carton",
        PackageType.CARTON,
        "Nepro",
        1000,
        (1770, 81, 96, 160, 727, 25, 35.4, 1050, 949, 844, 1050, 717),
    ),
    _formula(
        "nepro 1.8 1L ready-to-hang",
        PackageType.READY_TO_HANG,
        "Nepro",
        1000,
        (1770, 81, 96, 160, 727, 25, 35.4, 1050, 949, 844, 1050, 717),
    ),
    _formula(
        "glucerna 1.5 237 mL carton",
        PackageType.CARTON,
        "Glucerna",
        237,
        (356, 19.6, 17.8, 31.5, 180, 3.8, 15, 330, 480, 270, 190, 190),
    ),
    _formula(
        "glucerna 1.5 1L ready-to-hang",
        PackageType.READY_TO_HANG,
        "Glucerna",
        1000,
        (1500, 82.7, 75.1, 133, 759, 16, 63, 1390, 2220, 1140, 800, 800),
    ),
    _formula(
        "glucerna 1.2 237 mL carton",
        PackageType.CARTON,
        "Glucerna",
        237,
        (285, 14.2, 14.2, 27, 191, 3.8, 13, 270, 380, 220, 190, 190),
    ),
    _formula(
        "glucerna 1.2 1L ready-to-hang",
        PackageType.READY_TO_HANG,
        "Glucerna",
        1000,
        (1200, 60, 60, 114, 805, 16.1, 55, 1140, 1600, 930, 800, 800),
    ),
    _formula(
        "glucerna 1.2 1.5L ready-to-hang",
        PackageType.READY_TO_HANG,
        "Glucerna",
        1500,
        (1800, 90, 90, 171, 1210, 24.1, 82, 1710, 2410, 1390, 1200, 1200),
    ),
)
