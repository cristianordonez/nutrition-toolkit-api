"""Resolve extracted facility clues against trusted facility records."""

from __future__ import annotations

import typing

from ntk.defaults import DEFAULT_FACILITIES, DefaultFacility
from ntk.models.sql.facility import Facility, normalize_facility_name

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

    from ntk.repositories.facility_repo import FacilityRepo


class FacilityResolver:
    """Resolve canonical names, aliases, and external facility identifiers."""

    def __init__(
        self,
        repository: FacilityRepo,
        defaults: Iterable[DefaultFacility] = DEFAULT_FACILITIES,
    ) -> None:
        """Store the repository and build the configured alias lookup."""
        self.repository = repository
        self._canonical_name_by_alias = {
            normalize_facility_name(alias): default.name
            for default in defaults
            for alias in (default.name, *default.aliases)
        }

    def resolve(
        self,
        name: str | None = None,
        *,
        facility_identifier: str | None = None,
    ) -> Facility | None:
        """Return a trusted facility match without creating database rows."""
        identifier_match = (
            self.repository.get_by_facility_identifier(facility_identifier)
            if facility_identifier
            else None
        )
        name_match = self._resolve_name(name) if name else None
        if (
            identifier_match is not None
            and name_match is not None
            and identifier_match.id != name_match.id
        ):
            msg = "Facility identifier and name resolve to different facilities"
            raise ValueError(msg)
        return identifier_match or name_match

    def register_trusted(
        self,
        *,
        name: str,
        facility_identifier: str | None = None,
    ) -> Facility:
        """Explicitly register a facility supplied by a trusted structured source."""
        return self.repository.create(
            Facility(name=name, facility_identifier=facility_identifier),
        )

    def _resolve_name(self, name: str) -> Facility | None:
        direct_match = self.repository.get_by_name(name)
        if direct_match is not None:
            return direct_match
        canonical_name = self._canonical_name_by_alias.get(
            normalize_facility_name(name),
        )
        if canonical_name is None:
            return None
        return self.repository.get_by_name(canonical_name)


__all__ = ["FacilityResolver"]
