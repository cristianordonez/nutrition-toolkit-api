"""Nutrition EN Formulas."""

from __future__ import annotations

from ntk.models.formula import Formula, Nutrition

READY_TO_HANG_FORMULAS = {
    "jevity 1.2": Formula(
        name="jevity 1.2",
        consistency="nectar",
        nutrition=Nutrition(
            serving_size=1000,
            cal=1200,
            protein=55.5,
            fat=39.3,
            carbs=169.4,
            water=807,
        ),
    ),
    "jevity 1.5": Formula(
        name="jevity 1.5",
        consistency="nectar",
        nutrition=Nutrition(
            serving_size=1000,
            cal=1500,
            protein=63.8,
            fat=49.8,
            carbs=215.7,
            water=760,
        ),
    ),
    "osmolite 1.2": Formula(
        name="osmolite 1.2",
        consistency="nectar",
        nutrition=Nutrition(
            serving_size=1000,
            cal=1200,
            protein=55.5,
            fat=39.3,
            carbs=157.5,
            water=820,
        ),
    ),
    "osmolite 1.5": Formula(
        name="osmolite 1.5",
        consistency="nectar",
        nutrition=Nutrition(
            serving_size=1000,
            cal=1500,
            protein=62.7,
            fat=49.1,
            carbs=203.6,
            water=762,
        ),
    ),
    "katefarms 1.4": Formula(
        name="kate farms 1.4",
        consistency="nectar",
        nutrition=Nutrition(
            serving_size=1000,
            cal=1400,
            protein=62,
            fat=58,
            carbs=157,
            water=710,
        ),
    ),
    "katefarms pepite 1.5": Formula(
        name="kate farms peptide 1.5",
        consistency="nectar",
        nutrition=Nutrition(
            serving_size=1000,
            cal=1538,
            protein=74,
            fat=77,
            carbs=138,
            water=701,
        ),
    ),
}

OTHER_FORMULAS = {
    "jevity 1.2": Formula(
        name="jevity 1.2",
        consistency="nectar",
        nutrition=Nutrition(
            serving_size=237,
            cal=285,
            protein=13.2,
            fat=9.3,
            carbs=40.2,
            water=191,
        ),
    ),
    "jevity 1.5": Formula(
        name="jevity 1.5",
        consistency="nectar",
        nutrition=Nutrition(
            serving_size=237,
            cal=355,
            protein=15.1,
            fat=11.8,
            carbs=51.1,
            water=180,
        ),
    ),
    "osmolite 1.2": Formula(
        name="osmolite 1.2",
        consistency="nectar",
        nutrition=Nutrition(
            serving_size=237,
            cal=285,
            protein=13.2,
            fat=9.3,
            carbs=37.5,
            water=195,
        ),
    ),
    "osmolite 1.5": Formula(
        name="osmolite 1.5",
        consistency="nectar",
        nutrition=Nutrition(
            serving_size=237,
            cal=355,
            protein=14.9,
            fat=11.6,
            carbs=48.2,
            water=181,
        ),
    ),
    "katefarms 1.4": Formula(
        name="kate farms 1.4",
        consistency="nectar",
        nutrition=Nutrition(
            serving_size=325,
            cal=455,
            protein=20,
            fat=19,
            carbs=51,
            water=231,
        ),
    ),
    "katefarms 1.5": Formula(
        name="kate farms peptide 1.5",
        consistency="nectar",
        nutrition=Nutrition(
            serving_size=325,
            cal=500,
            protein=24,
            fat=25,
            carbs=45,
            water=228,
        ),
    ),
}
