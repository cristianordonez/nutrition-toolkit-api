"""FastAPI routes for persisted person data."""

from __future__ import annotations

import typing

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session  # noqa: TC002

from ntk.controllers.persons.clinical_facts import (
    PersonClinicalFactsController,
    PersonClinicalFactsOptions,
)
from ntk.controllers.persons.list import PersonListController, PersonListOptions
from ntk.controllers.persons.ncps import (
    PersonNCPsController,
    PersonNCPsOptions,
)
from ntk.controllers.persons.weights import (
    PersonWeightsController,
    PersonWeightsOptions,
)
from ntk.database.db import get_session
from ntk.defaults import (
    ADMIN_PERMISSION,
    NCP_READ_PERMISSION,
    PERSONS_READ_PERMISSION,
)
from ntk.models.sql.clinical import PersonClinicalFact, PersonWeight
from ntk.models.sql.person import Person, PersonClinicalNote
from ntk.presentation.api.middleware import rate_limit, require_any_permission
from ntk.repositories.food_repo import FoodRepo
from ntk.repositories.person_repo import PersonRepo
from ntk.services.calculators.tubefeed_calculator import TubeFeedCalculator
from ntk.services.person.detail_builder import PersonDetailBuilder
from ntk.services.person.person_service import PersonService

router = APIRouter()

_READ_DEPENDENCIES = [
    Depends(require_any_permission([ADMIN_PERMISSION, PERSONS_READ_PERMISSION])),
]

_NCP_READ_DEPENDENCIES = [
    Depends(require_any_permission([ADMIN_PERMISSION, NCP_READ_PERMISSION])),
]


@router.get(
    "/persons/",
    response_model=list[Person],
    dependencies=[
        *_READ_DEPENDENCIES,
        Depends(rate_limit(60, window=3600, scope="persons-list")),
    ],
)
async def list_persons(
    session: typing.Annotated[Session, Depends(get_session)],
) -> list[Person]:
    """Return all persons."""
    return PersonListController(session).run(PersonListOptions()).result.persons


@router.get(
    "/persons/{person_id}",
    response_model=dict[str, object],
    dependencies=[
        *_READ_DEPENDENCIES,
        Depends(rate_limit(60, window=3600, scope="persons-context")),
    ],
)
async def get_person_detail(
    person_id: int,
    session: typing.Annotated[Session, Depends(get_session)],
) -> Response:
    """Return NCP-ready clinical context for one person."""
    try:
        service = PersonService(
            PersonRepo(session),
            person_detail_builder=PersonDetailBuilder(
                TubeFeedCalculator(FoodRepo(session)),
            ),
        )
        detail = service.get_person_detail_by_id(
            person_id,
        )
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    return Response(
        content=detail.model_dump_json(indent=2),
        media_type="application/json",
    )


@router.get(
    "/persons/{person_id}/nutrition-care-processes",
    response_model=list[PersonClinicalNote],
    dependencies=[
        *_NCP_READ_DEPENDENCIES,
        Depends(rate_limit(60, window=3600, scope="persons-ncps")),
    ],
)
async def get_person_ncps(
    person_id: int,
    session: typing.Annotated[Session, Depends(get_session)],
) -> list[PersonClinicalNote]:
    """Return Nutrition Care Processes for one person."""
    output = PersonNCPsController(session).run(
        PersonNCPsOptions(person_ids=[person_id]),
    )
    return output.result.ncps


@router.get(
    "/persons/{person_id}/weights",
    response_model=list[PersonWeight],
    dependencies=[
        *_READ_DEPENDENCIES,
        Depends(rate_limit(60, window=3600, scope="persons-weights")),
    ],
)
async def get_person_weights(
    person_id: int,
    session: typing.Annotated[Session, Depends(get_session)],
) -> list[PersonWeight]:
    """Return weight history for one person."""
    output = PersonWeightsController(session).run(
        PersonWeightsOptions(person_ids=[person_id]),
    )
    return output.result.weights


@router.get(
    "/persons/{person_id}/clinical-facts",
    response_model=list[PersonClinicalFact],
    dependencies=[
        *_READ_DEPENDENCIES,
        Depends(rate_limit(60, window=3600, scope="persons-clinical-facts")),
    ],
)
async def get_person_clinical_facts(
    person_id: int,
    session: typing.Annotated[Session, Depends(get_session)],
) -> list[PersonClinicalFact]:
    """Return clinical facts for one person."""
    output = PersonClinicalFactsController(session).run(
        PersonClinicalFactsOptions(person_ids=[person_id]),
    )
    return output.result.clinical_facts
