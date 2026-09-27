"""Attributing an unknown document's facts to the patient it names.

The extractor windows a document into 600-token chunks and asks the model to
read facts out of each one. A discharge packet names its patient in a header
on every page, but a window taken from the middle of a medication table has no
header in it -- so real facts come back attached to nobody, and persistence
refuses the whole batch because a person cannot be created from facts alone.
"""

from __future__ import annotations

from datetime import date

from engine.models.extracted_fact_create import ExtractedFactCreate, WeightPayload
from engine.pipelines.person.ingestion.extract.unknown_file import (
    UnknownFileExtractor,
)

_BIRTH_DATE = date(1982, 7, 20)


def _fact(
    name: str | None = None,
    identifier: str | None = None,
    birth_date: date | None = None,
) -> ExtractedFactCreate:
    return ExtractedFactCreate(
        source_person_name=name,
        source_person_identifier=identifier,
        date_of_birth=birth_date,
        payload=WeightPayload(weight_lb=150, measured_at=date(2026, 9, 14)),
        confidence=1.0,
        confidence_reason="test",
    )


def _attribute(facts: list[ExtractedFactCreate]) -> list[ExtractedFactCreate]:
    return UnknownFileExtractor._attribute_to_document_subject(  # noqa: SLF001
        facts,
        "Mark_Diawatan_Discharge_Paperwork.pdf",
    )


def test_unattributed_chunks_take_the_documents_subject() -> None:
    """The reported failure: a chunk with no header lost its patient."""
    facts = _attribute(
        [
            _fact("Diawatan, Mark", "03526134", _BIRTH_DATE),
            _fact(),
            _fact(),
        ],
    )

    for fact in facts:
        assert fact.source_person_name == "Diawatan, Mark"
        assert fact.source_person_identifier == "03526134"
        assert fact.date_of_birth == _BIRTH_DATE


def test_a_chunk_naming_the_patient_without_a_birth_date_is_completed() -> None:
    """The real regression: identity arrives in pieces, not all-or-nothing.

    A chunk that carries the name but no birth date and no identifier is
    rejected by persistence just as surely as one that names nobody, so
    filling only the nameless chunks left the batch still failing.
    """
    facts = _attribute(
        [
            _fact("Diawatan, Mark", "03526134", _BIRTH_DATE),
            _fact("Diawatan, Mark"),
            _fact("Diawatan, Mark", birth_date=_BIRTH_DATE),
        ],
    )

    for fact in facts:
        assert fact.source_person_identifier == "03526134"
        assert fact.date_of_birth == _BIRTH_DATE


def test_pieces_of_one_identity_combine_across_chunks() -> None:
    """No single chunk is complete, but together they identify one person."""
    facts = _attribute(
        [
            _fact("Diawatan, Mark"),
            _fact(identifier="03526134"),
            _fact(birth_date=_BIRTH_DATE),
        ],
    )

    for fact in facts:
        assert fact.source_person_name == "Diawatan, Mark"
        assert fact.source_person_identifier == "03526134"
        assert fact.date_of_birth == _BIRTH_DATE


def test_the_same_name_written_two_ways_is_one_person() -> None:
    """Headers print "Diawatan, Mark"; running text says "Mark Diawatan"."""
    facts = _attribute(
        [
            _fact("Diawatan, Mark", "03526134", _BIRTH_DATE),
            _fact("Mark Diawatan"),
        ],
    )

    assert facts[1].date_of_birth == _BIRTH_DATE


def test_a_conflicting_birth_date_blocks_attribution() -> None:
    """One name, two birth dates: two people, or a misread. Either way, stop."""
    facts = _attribute(
        [
            _fact("Diawatan, Mark", birth_date=_BIRTH_DATE),
            _fact("Diawatan, Mark", birth_date=date(1950, 1, 1)),
            _fact(identifier="03526134"),
        ],
    )

    assert facts[0].source_person_identifier is None


def test_a_conflicting_identifier_blocks_attribution() -> None:
    facts = _attribute(
        [
            _fact("Diawatan, Mark", "03526134"),
            _fact("Diawatan, Mark", "99999999"),
            _fact(birth_date=_BIRTH_DATE),
        ],
    )

    assert facts[0].date_of_birth is None


def test_one_subject_is_recognized_across_differing_letter_case() -> None:
    """A header reads "DIAWATAN, MARK" on one page and "Diawatan, Mark" on another."""
    facts = _attribute(
        [
            _fact("DIAWATAN, MARK", "03526134", _BIRTH_DATE),
            _fact("Diawatan, Mark", "03526134", _BIRTH_DATE),
            _fact(),
        ],
    )

    assert facts[2].source_person_name == "DIAWATAN, MARK"


def test_a_document_naming_two_people_is_never_guessed_at() -> None:
    """The safety case: an unattributed order must not be filed under a guess."""
    facts = _attribute(
        [
            _fact("Diawatan, Mark", "03526134", _BIRTH_DATE),
            _fact("Other, Person", "99999999", date(1970, 1, 1)),
            _fact(),
        ],
    )

    assert facts[2].source_person_name is None
    assert facts[2].source_person_identifier is None
    assert facts[2].date_of_birth is None


def test_facts_that_name_nobody_at_all_are_left_alone() -> None:
    facts = _attribute([_fact(), _fact()])

    assert all(fact.source_person_name is None for fact in facts)


def test_a_chunk_that_names_its_own_patient_is_not_overwritten() -> None:
    """Attribution fills gaps; it never relabels a value a fact already has."""
    facts = _attribute(
        [
            _fact("Diawatan, Mark", "03526134", _BIRTH_DATE),
            # Same person, but this chunk spells the name out in full. The
            # spelling it came with is the one it keeps.
            _fact("Mark Diawatan", "03526134", _BIRTH_DATE),
        ],
    )

    assert [fact.source_person_name for fact in facts] == [
        "Diawatan, Mark",
        "Mark Diawatan",
    ]


def test_an_identifier_alone_is_enough_to_carry_forward() -> None:
    """Some headers print only the MRN, which is still an identity."""
    facts = _attribute([_fact(identifier="03526134"), _fact()])

    assert facts[1].source_person_identifier == "03526134"
