"""Return clinical facts for selected residents."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.output import Output
from ntk.models.sql.clinical import ResidentClinicalFact  # noqa: TC001
from ntk.repositories.resident_repo import ResidentRepo

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class ResidentClinicalFactsOptions(BaseModel):
    """Resident IDs whose clinical facts should be returned."""

    resident_ids: list[int] = Field(min_length=1)


class ResidentClinicalFactsResult(BaseModel):
    """Clinical facts belonging to requested residents."""

    clinical_facts: list[ResidentClinicalFact]


class ResidentClinicalFactsController(BaseController):
    """Retrieve clinical facts for one or more residents."""

    name = "clinical-facts"
    help = "Get clinical facts by resident ID"
    options_model = ResidentClinicalFactsOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(
        self,
        options: ResidentClinicalFactsOptions,
    ) -> Output[ResidentClinicalFactsResult]:
        """Return clinical facts for the supplied resident IDs."""
        with controller_session(self.session) as session:
            facts = ResidentRepo(session).get_clinical_facts_by_resident_ids(
                options.resident_ids,
            )
        return Output(
            result=ResidentClinicalFactsResult(clinical_facts=facts),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "ResidentClinicalFactsController",
    "ResidentClinicalFactsOptions",
    "ResidentClinicalFactsResult",
]
