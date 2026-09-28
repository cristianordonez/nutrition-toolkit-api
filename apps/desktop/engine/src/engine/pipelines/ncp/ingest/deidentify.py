"""Scrub identifiers that redaction leaves behind in NCP note text.

A "deidentified" PCC report has its header fields blacked out, but the note
bodies are free text written about a named resident, and redaction tools only
catch what they were pointed at. What survives is predictable: family members
named beside their relationship ("son/Umesh", "DIL, Helen"), the resident
addressed by title or first name ("Mr. Ray", "Han is a 92 y/o"), staff named
by role ("HD RD Dang"), the dialysis centre, hospital or hospice the resident
attends, street addresses, full dates, and ages over 89 (which HIPAA's Safe
Harbor rule treats as an identifier on their own).

This is deterministic pattern matching, not a guarantee. It removes the
forms that recur in these reports so the stored examples carry clinical
reasoning rather than people. Anything it misses stays in the example, so a
report should still be de-identified at the source before it is ingested.
"""

from __future__ import annotations

import re

NAME = "[NAME]"
FACILITY = "[FACILITY]"
ADDRESS = "[ADDRESS]"
DATE = "[DATE]"
CONTACT = "[CONTACT]"

#: Relationship words that are written next to a family member's name, in
#: any case ("DIL, Helen" and "her dil, Helen" both occur).
_RELATION = (
    r"(?i:son|daughter|nephew|niece|brother|sister|wife|husband|spouse|mother|"
    r"father|granddaughter|grandson|grandchild|cousin|aunt|uncle|friend|"
    r"guardian|dtr|dau|DIL|SIL|POA|HCP|RP)"
)

#: Capitalised words that open a clinical sentence or follow a relationship
#: and are not names, so "Rt is a 70 yo female" and "son, Pt agreeable" are
#: left alone while "Han is a 92 y/o" and "son, Samit" are not.
_NOT_A_NAME = (
    "Resident|Patient|She|They|Who|Mrs|Male|Female|This|The|Currently|Now|"
    "Summary|Recommendations|Overview|Also|Weight|Today|Will|Per|And|Family|"
    "Called|Spoke|Aware|Agreeable|Updated|Declined|Requested|Stated"
)

#: One capitalised word that could be a given name. Two-letter words are
#: left out because the notes' abbreviations ("Pt", "Rt", "Wt") are too.
_PROPER = r"[A-Z][a-z]{2,20}"
_NAME_WORD = rf"(?!(?:{_NOT_A_NAME})\b){_PROPER}"

_FACILITY_WORDS = (
    r"(?:Hospital|Hospice|hospice|Medical Center|Center|center|Centre|"
    r"Rehabilitation|Rehab|Nursing Home|Kidney Care|Dialysis)"
)

_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # Contact details.
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), CONTACT),
    (re.compile(r"(?<!\d)\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)"), CONTACT),
    # Street addresses, with an optional town and state after them.
    (
        re.compile(
            r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s+){1,3}"
            r"(?:Ave|Avenue|St|Street|Rd|Road|Blvd|Boulevard|Dr|Drive|Ln|Lane|"
            r"Way|Pike|Hwy|Highway|Ct|Court|Pl|Place)\b\.?"
            r"(?:,\s*(?:[A-Z][a-z]+\s?){1,3})?(?:,\s*[A-Z]{2}\b)?",
        ),
        ADDRESS,
    ),
    # Named dialysis providers, with the branch or town that follows them.
    (
        re.compile(
            r"\b(?:DaVita|Davita|DAVITA|Fresenius)\b"
            r"(?:[ \t]+(?:[A-Z][a-z]{2,}|care|center))*"
            r"(?:,[ \t]*[A-Z][a-z]{2,}\b)?",
        ),
        FACILITY,
    ),
    # Other named facilities: capitalised words ending in a facility word,
    # or a name with one plain word before "center" ("Cypress garden center").
    (
        re.compile(rf"\b(?:{_PROPER}[ \t]+){{1,3}}{_FACILITY_WORDS}\b"),
        FACILITY,
    ),
    (re.compile(rf"\b{_NAME_WORD}[ \t]+[a-z]+[ \t]+center\b"), FACILITY),
    # Family named beside the relationship: "son/Umesh", "Betty/daughter",
    # "DIL, Helen", "daughter (Rupal)".
    (
        re.compile(rf"\b({_RELATION})[ \t]*(?:/|,|\()[ \t]*{_NAME_WORD}\)?"),
        rf"\1 {NAME}",
    ),
    (re.compile(rf"\b{_NAME_WORD}[ \t]*/[ \t]*({_RELATION})\b"), rf"{NAME}/\1"),
    # Titles: "Mr. Ray", "Mrs Smith".
    (re.compile(rf"\b(Mr|Mrs|Ms|Miss|Dr)\.?[ \t]+{_NAME_WORD}\b"), rf"\1. {NAME}"),
    # Staff named by role: "HD RD Dang", "Dang - RD at HD".
    (re.compile(rf"\b((?:HD|renal|Renal)[ \t]+RD)[ \t]+{_NAME_WORD}\b"), rf"\1 {NAME}"),
    (re.compile(rf"\b{_NAME_WORD}[ \t]*-[ \t]*(RD at HD)\b"), rf"{NAME} - \1"),
    # Full dates.
    (
        re.compile(
            r"(?<![\d./])(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])"
            r"/(?:\d{4}|\d{2})(?![\d/])",
        ),
        DATE,
    ),
)

#: A resident's given name opening a sentence about them: "Han is a 92 y/o".
_LEADING_NAME = re.compile(
    rf"\b(?P<name>{_NAME_WORD})(?P<gap>[ \t]+)(?=is an?[ \t]+\d{{1,3}}[ \t]*"
    r"(?:y/?o|yo|y\.o|year))",
)

#: Ages over 89, which Safe Harbor requires be reported only as "90 or over".
_OLD_AGE = re.compile(
    r"\b(?P<age>9\d|1[0-2]\d)(?P<sep>[ \t-]*)"
    r"(?P<unit>y/o|yo|y\.o\.?|year[s]?[- ]old|years?\b)",
    flags=re.IGNORECASE,
)


class NoteDeidentifier:
    """Replace the identifiers that survive redaction in PCC note text."""

    def deidentify(self, text: str) -> str:
        """Return ``text`` with names, places, contacts and old ages removed."""
        for pattern, replacement in _RULES:
            text = pattern.sub(replacement, text)
        text = _LEADING_NAME.sub(rf"{NAME}\g<gap>", text)
        return _OLD_AGE.sub(r"90+\g<sep>\g<unit>", text)


__all__ = ["NoteDeidentifier"]
