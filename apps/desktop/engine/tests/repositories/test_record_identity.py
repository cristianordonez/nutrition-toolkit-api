"""Dedup identity must agree with the table constraints it protects.

A record's natural identity is what decides whether an incoming row is the
same as one already held. When that disagrees with the UNIQUE constraint on
the table, ingestion inserts a second copy and the database rejects the whole
batch.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from engine.models.clinical_fact_registry import fact_envelope
from engine.models.clinical_facts import PersonLab, PersonWeight


def _identity(record: PersonLab | PersonWeight, fact_type: str) -> str:
    return fact_envelope(record, fact_type)["identity_hash"]


def test_a_lab_is_one_record_whether_or_not_its_date_carries_a_timezone() -> None:
    """Deterministic extractors build aware datetimes; AI-parsed ones are naive.

    SQLite stores no offset, so both land on the row that
    UniqueConstraint(person_id, name, observed_at) protects. Treating them as
    two records inserted a duplicate and failed the batch.
    """
    aware = PersonLab(
        person_id=95,
        name="Albumin",
        result="3.1",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    naive = PersonLab(
        person_id=95,
        name="Albumin",
        result="3.1",
        observed_at=datetime(2026, 8, 1),  # noqa: DTZ001 - naive on purpose
    )

    assert _identity(aware, "lab") == _identity(naive, "lab")


def test_an_offset_is_normalized_rather_than_dropped() -> None:
    """Same instant, different offsets, is one observation."""
    utc = PersonLab(
        person_id=1,
        name="Sodium",
        result="133",
        observed_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
    )
    shifted = PersonLab(
        person_id=1,
        name="Sodium",
        result="133",
        observed_at=datetime(2026, 8, 1, 9, tzinfo=timezone(timedelta(hours=-3))),
    )

    assert _identity(utc, "lab") == _identity(shifted, "lab")


def test_genuinely_different_dates_stay_different() -> None:
    """Normalizing must not collapse distinct observations into one."""
    first = PersonLab(
        person_id=1,
        name="Sodium",
        result="133",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    second = PersonLab(
        person_id=1,
        name="Sodium",
        result="131",
        observed_at=datetime(2026, 8, 2, tzinfo=UTC),
    )

    assert _identity(first, "lab") != _identity(second, "lab")


def test_weights_share_the_same_normalization() -> None:
    """Weights are keyed on measured_at and have the same mixed-source risk."""
    aware = PersonWeight(
        person_id=2,
        weight_lb=150,
        measured_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    naive = PersonWeight(
        person_id=2,
        weight_lb=150,
        measured_at=datetime(2026, 8, 1),  # noqa: DTZ001 - naive on purpose
    )

    assert _identity(aware, "weight") == _identity(naive, "weight")
