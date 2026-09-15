"""Simple application operations for persisted Nutrition Care Processes."""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from api.models.sql.ncp import NutritionCareProcess
    from api.repositories.ncp_repo import NCPRepo


class NutritionCareProcessService:
    """Expose simple ncp reads above the repository boundary."""

    def __init__(self, repository: NCPRepo) -> None:
        """Store the ncp repository."""
        self.repository = repository

    def get(
        self,
        ncp_id: int,
        person_identifier: str,
    ) -> NutritionCareProcess | None:
        """Return one ncp by its database identifier."""
        return self.repository.get_ncp(ncp_id, person_identifier)

    def list_ncps(self, person_identifier: str) -> list[NutritionCareProcess]:
        """Return all of one person's ncps newest first."""
        return self.repository.list_ncps(person_identifier)


__all__ = ["NutritionCareProcessService"]
