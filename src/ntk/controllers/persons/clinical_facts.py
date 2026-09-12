"""Return clinical facts for selected persons."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.output import Output
from ntk.models.sql.clinical import PersonClinicalFact  # noqa: TC001
from ntk.repositories.person_repo import PersonRepo

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class PersonClinicalFactsOptions(BaseModel):
    """Person IDs whose clinical facts should be returned."""

    person_ids: list[int] = Field(min_length=1)


class PersonClinicalFactsResult(BaseModel):
    """Clinical facts belonging to requested persons."""

    clinical_facts: list[PersonClinicalFact]


class PersonClinicalFactsController(BaseController):
    """Retrieve clinical facts for one or more persons."""

    name = "clinical-facts"
    help = "Get clinical facts by person ID"
    options_model = PersonClinicalFactsOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(
        self,
        options: PersonClinicalFactsOptions,
    ) -> Output[PersonClinicalFactsResult]:
        """Return clinical facts for the supplied person IDs."""
        with controller_session(self.session) as session:
            facts = PersonRepo(session).get_clinical_facts_by_person_ids(
                options.person_ids,
            )
        return Output(
            result=PersonClinicalFactsResult(clinical_facts=facts),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "PersonClinicalFactsController",
    "PersonClinicalFactsOptions",
    "PersonClinicalFactsResult",
]
