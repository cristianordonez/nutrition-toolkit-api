from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DefaultFacility:
    """Trusted facility metadata seeded into the local database at startup."""

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
