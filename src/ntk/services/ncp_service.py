"""Simple application operations for persisted Nutrition Care Processes."""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from ntk.models.sql.person import PersonClinicalNote
    from ntk.repositories.clinical_note_repo import ClinicalNoteRepo


class NutritionCareProcessService:
    """Expose simple ncp reads above the repository boundary."""

    def __init__(self, repository: ClinicalNoteRepo) -> None:
        """Store the ncp repository."""
        self.repository = repository

    def get(self, ncp_id: int) -> PersonClinicalNote | None:
        """Return one ncp by its database identifier."""
        return self.repository.get_ncp(ncp_id)

    def list_ncps(self) -> list[PersonClinicalNote]:
        """Return all ncps newest first."""
        return self.repository.list_ncps()


__all__ = ["NutritionCareProcessService"]
