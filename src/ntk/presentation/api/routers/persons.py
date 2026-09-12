"""FastAPI routes for persisted person data."""

from __future__ import annotations

import typing

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session  # noqa: TC002

from ntk.controllers.persons.assessments import (
    PersonAssessmentsController,
    PersonAssessmentsOptions,
)
from ntk.controllers.persons.clinical_facts import (
    PersonClinicalFactsController,
    PersonClinicalFactsOptions,
)
from ntk.controllers.persons.list import PersonListController, PersonListOptions
from ntk.controllers.persons.weights import (
    PersonWeightsController,
    PersonWeightsOptions,
)
from ntk.database.db import get_session
from ntk.defaults import (
    ADMIN_PERMISSION,
    ASSESSMENTS_READ_PERMISSION,
    PERSONS_READ_PERMISSION,
)
from ntk.models.sql.clinical import PersonClinicalFact, PersonWeight
from ntk.models.sql.person import Person, PersonAssessment
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

_ASSESSMENT_READ_DEPENDENCIES = [
    Depends(require_any_permission([ADMIN_PERMISSION, ASSESSMENTS_READ_PERMISSION])),
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
    """Return assessment-ready clinical context for one person."""
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
    "/persons/{person_id}/assessments",
    response_model=list[PersonAssessment],
    dependencies=[
        *_ASSESSMENT_READ_DEPENDENCIES,
        Depends(rate_limit(60, window=3600, scope="persons-assessments")),
    ],
)
async def get_person_assessments(
    person_id: int,
    session: typing.Annotated[Session, Depends(get_session)],
) -> list[PersonAssessment]:
    """Return assessments for one person."""
    output = PersonAssessmentsController(session).run(
        PersonAssessmentsOptions(person_ids=[person_id]),
    )
    return output.result.assessments


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
