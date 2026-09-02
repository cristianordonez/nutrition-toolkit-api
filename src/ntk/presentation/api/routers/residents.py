"""FastAPI routes for persisted resident data."""

from __future__ import annotations

import typing

from fastapi import APIRouter, Depends
from sqlmodel import Session  # noqa: TC002

from ntk.controllers.residents.assessments import (
    ResidentAssessmentsController,
    ResidentAssessmentsOptions,
)
from ntk.controllers.residents.clinical_facts import (
    ResidentClinicalFactsController,
    ResidentClinicalFactsOptions,
)
from ntk.controllers.residents.list import ResidentListController, ResidentListOptions
from ntk.controllers.residents.weights import (
    ResidentWeightsController,
    ResidentWeightsOptions,
)
from ntk.database.db import get_session
from ntk.defaults import (
    ADMIN_PERMISSION,
    ASSESSMENTS_READ_PERMISSION,
    RESIDENTS_READ_PERMISSION,
)
from ntk.models.sql.clinical import ResidentClinicalFact, ResidentWeight
from ntk.models.sql.resident import Resident, ResidentAssessment
from ntk.presentation.api.middleware import rate_limit, require_any_permission

router = APIRouter()

_READ_DEPENDENCIES = [
    Depends(require_any_permission([ADMIN_PERMISSION, RESIDENTS_READ_PERMISSION])),
]

_ASSESSMENT_READ_DEPENDENCIES = [
    Depends(require_any_permission([ADMIN_PERMISSION, ASSESSMENTS_READ_PERMISSION])),
]


@router.get(
    "/residents/",
    response_model=list[Resident],
    dependencies=[
        *_READ_DEPENDENCIES,
        Depends(rate_limit(60, window=3600, scope="residents-list")),
    ],
)
async def list_residents(
    session: typing.Annotated[Session, Depends(get_session)],
) -> list[Resident]:
    """Return all residents."""
    return ResidentListController(session).run(ResidentListOptions()).result.residents


@router.get(
    "/residents/{resident_id}/assessments",
    response_model=list[ResidentAssessment],
    dependencies=[
        *_ASSESSMENT_READ_DEPENDENCIES,
        Depends(rate_limit(60, window=3600, scope="residents-assessments")),
    ],
)
async def get_resident_assessments(
    resident_id: int,
    session: typing.Annotated[Session, Depends(get_session)],
) -> list[ResidentAssessment]:
    """Return assessments for one resident."""
    output = ResidentAssessmentsController(session).run(
        ResidentAssessmentsOptions(resident_ids=[resident_id]),
    )
    return output.result.assessments


@router.get(
    "/residents/{resident_id}/weights",
    response_model=list[ResidentWeight],
    dependencies=[
        *_READ_DEPENDENCIES,
        Depends(rate_limit(60, window=3600, scope="residents-weights")),
    ],
)
async def get_resident_weights(
    resident_id: int,
    session: typing.Annotated[Session, Depends(get_session)],
) -> list[ResidentWeight]:
    """Return weight history for one resident."""
    output = ResidentWeightsController(session).run(
        ResidentWeightsOptions(resident_ids=[resident_id]),
    )
    return output.result.weights


@router.get(
    "/residents/{resident_id}/clinical-facts",
    response_model=list[ResidentClinicalFact],
    dependencies=[
        *_READ_DEPENDENCIES,
        Depends(rate_limit(60, window=3600, scope="residents-clinical-facts")),
    ],
)
async def get_resident_clinical_facts(
    resident_id: int,
    session: typing.Annotated[Session, Depends(get_session)],
) -> list[ResidentClinicalFact]:
    """Return clinical facts for one resident."""
    output = ResidentClinicalFactsController(session).run(
        ResidentClinicalFactsOptions(resident_ids=[resident_id]),
    )
    return output.result.clinical_facts
