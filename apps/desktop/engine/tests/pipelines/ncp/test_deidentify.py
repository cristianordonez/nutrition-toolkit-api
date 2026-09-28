from __future__ import annotations

import pytest

from engine.pipelines.ncp.ingest.deidentify import NoteDeidentifier


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Spoke with nephew/Jose about diet.", "Spoke with nephew [NAME] about diet."),
        ("Betty/daughter at bedside.", "[NAME]/daughter at bedside."),
        ("Updated DIL, Helen by phone.", "Updated DIL [NAME] by phone."),
        (
            "RD left VM for her dil, Helen, re: diet.",
            "RD left VM for her dil [NAME], re: diet.",
        ),
        ("Spoke with dtr, Helen.", "Spoke with dtr [NAME]."),
        (
            "Discharged to Cypress garden center today.",
            "Discharged to [FACILITY] today.",
        ),
        ("Mr. Ray ate 50% of lunch.", "Mr. [NAME] ate 50% of lunch."),
        ("Spoke with HD RD Dang today.", "Spoke with HD RD [NAME] today."),
        ("Per Dang - RD at HD, labs ok.", "Per [NAME] - RD at HD, labs ok."),
        ("Han is a 85 y/o female.", "[NAME] is a 85 y/o female."),
        ("Rt is a 85 y/o female.", "Rt is a 85 y/o female."),
        ("Rt is a 92 y/o female.", "Rt is a 90+ y/o female."),
        ("Rt is a 103 yo male.", "Rt is a 90+ yo male."),
        (
            "Readmitted from Ramapo Ridge Psychiatric Hospital.",
            "Readmitted from [FACILITY].",
        ),
        ("Now with Serenity hospice.", "Now with [FACILITY]."),
        ("HD at Davita Edison MWF.", "HD at [FACILITY] MWF."),
        (
            "HD at Davita 241 Durham Ave, South Plainfield, NJ MWF.",
            "HD at [FACILITY] [ADDRESS] MWF.",
        ),
        ("Admitted 03/14/2025 from hospital.", "Admitted [DATE] from hospital."),
        ("Call 732-555-0142 for updates.", "Call [CONTACT] for updates."),
    ],
)
def test_deidentify_replaces_identifiers(text: str, expected: str) -> None:
    assert NoteDeidentifier().deidentify(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        # Clinical numbers that look like dates or ages must survive.
        "Wt change 30/90/180 days: -1.2%, -3%, -5%.",
        "Albumin 3.1, Hgb 9.1/28.",
        "Menu per Crandall, regular texture.",
        "Resident is on a 2 gm Na diet, 1500 mL fluid restriction.",
        "Weight 92 lbs, BMI 17.",
        "Spoke with son, Pt agreeable to supplement.",
        "Returned from hospital, readmitted to unit.",
    ],
)
def test_deidentify_leaves_clinical_text(text: str) -> None:
    assert NoteDeidentifier().deidentify(text) == text
