"""FastAPI routes for nutrition assessment ingestion."""

from __future__ import annotations

import typing

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlmodel import Session  # noqa: TC002

from ntk.agents.assessment_agent import AssessmentGenerationTimeoutError
from ntk.controllers.assessment.finalize import (
    AssessmentFinalizeController,
    AssessmentFinalizeOptions,
)
from ntk.controllers.assessment.generation import (
    AssessmentGenerationController,
    AssessmentGenerationOptions,
    GeneratedResidentAssessment,
)
from ntk.controllers.assessment.get import (
    AssessmentGetCommandController,
    AssessmentGetOptions,
)
from ntk.controllers.assessment.import_assessments import (
    AssessmentImportController,
    AssessmentImportResult,
)
from ntk.controllers.assessment.list import (
    AssessmentListController,
    AssessmentListOptions,
)
from ntk.controllers.assessment.sync import (
    AssessmentSyncController,
    AssessmentSyncOptions,
)
from ntk.controllers.assessment.update import (
    AssessmentUpdateController,
    AssessmentUpdateOptions,
    AssessmentUpdateRequest,
)
from ntk.controllers.uploads import UploadValidationError
from ntk.database.db import get_session
from ntk.defaults import (
    ADMIN_PERMISSION,
    ASSESSMENTS_READ_PERMISSION,
    ASSESSMENTS_WRITE_PERMISSION,
)
from ntk.models.sql.resident import ResidentAssessment
from ntk.presentation.api.middleware import rate_limit, require_any_permission
from ntk.services.assessment import AssessmentSyncResult

router = APIRouter()


@router.get(
    "/assessments",
    response_model=list[ResidentAssessment],
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, ASSESSMENTS_READ_PERMISSION],
            ),
        ),
        Depends(rate_limit(60, window=3600, scope="assessments-list")),
    ],
)
async def list_assessments(
    session: typing.Annotated[Session, Depends(get_session)],
) -> list[ResidentAssessment]:
    """Return all resident assessments."""
    return (
        AssessmentListController(session)
        .run(
            AssessmentListOptions(),
        )
        .result.assessments
    )


@router.get(
    "/assessments/{assessment_id}",
    response_model=ResidentAssessment,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, ASSESSMENTS_READ_PERMISSION],
            ),
        ),
        Depends(rate_limit(60, window=3600, scope="assessments-get")),
    ],
)
async def get_assessment(
    assessment_id: int,
    session: typing.Annotated[Session, Depends(get_session)],
) -> ResidentAssessment:
    """Return one resident assessment by ID."""
    try:
        output = AssessmentGetCommandController(session).run(
            AssessmentGetOptions(assessment_id=assessment_id),
        )
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    return output.result.assessment


@router.patch(
    "/assessments/{assessment_id}",
    response_model=ResidentAssessment,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, ASSESSMENTS_WRITE_PERMISSION],
            ),
        ),
        Depends(rate_limit(30, window=3600, scope="assessments-update")),
    ],
)
async def update_assessment(
    assessment_id: int,
    request: AssessmentUpdateRequest,
    session: typing.Annotated[Session, Depends(get_session)],
) -> ResidentAssessment:
    """Update editable fields on one resident assessment."""
    try:
        output = await AssessmentUpdateController(session).run(
            AssessmentUpdateOptions(
                assessment_id=assessment_id,
                **request.model_dump(),
            ),
        )
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return output.result


@router.post(
    "/assessments/{assessment_id}/finalize",
    response_model=ResidentAssessment,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, ASSESSMENTS_WRITE_PERMISSION],
            ),
        ),
        Depends(rate_limit(30, window=3600, scope="assessments-finalize")),
    ],
)
async def finalize_assessment(
    assessment_id: int,
    session: typing.Annotated[Session, Depends(get_session)],
) -> ResidentAssessment:
    """Mark one resident assessment as finalized."""
    try:
        output = await AssessmentFinalizeController(session).run(
            AssessmentFinalizeOptions(assessment_id=assessment_id),
        )
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    return output.result


@router.post(
    "/assessments/sync",
    response_model=AssessmentSyncResult,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, ASSESSMENTS_WRITE_PERMISSION],
            ),
        ),
        Depends(rate_limit(20, window=3600, scope="assessments-sync")),
    ],
)
async def sync_assessments(
    session: typing.Annotated[Session, Depends(get_session)],
) -> AssessmentSyncResult:
    """Synchronize historical nutrition assessments and their embeddings."""
    output = await AssessmentSyncController(session).run(AssessmentSyncOptions())
    return output.result


@router.post(
    "/assessments/generate",
    response_model=list[GeneratedResidentAssessment],
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, ASSESSMENTS_WRITE_PERMISSION],
            ),
        ),
        Depends(rate_limit(25, window=3600, scope="assessments-generate")),
    ],
)
async def generate_assessments(
    options: AssessmentGenerationOptions,
    session: typing.Annotated[Session, Depends(get_session)],
) -> list[GeneratedResidentAssessment]:
    """Generate assessments from external resident identifiers and context."""
    try:
        output = await AssessmentGenerationController(session).run(options)
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except AssessmentGenerationTimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(error),
        ) from error
    return output.result.assessments


@router.post(
    "/assessments/import",
    response_model=AssessmentImportResult,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, ASSESSMENTS_WRITE_PERMISSION],
            ),
        ),
        Depends(rate_limit(20, window=3600, scope="assessments-import")),
    ],
)
async def import_assessments(
    file: typing.Annotated[
        UploadFile,
        File(description="PCC progress-note report PDF"),
    ],
    *,
    overwrite: typing.Annotated[bool, Form()] = False,
    created_by: typing.Annotated[str | None, Form()] = None,
    session: typing.Annotated[Session | None, Depends(get_session)] = None,
) -> AssessmentImportResult:
    """Import nutrition notes from one PCC progress-note report."""
    try:
        output = await AssessmentImportController(session).run_upload(
            file,
            overwrite=overwrite,
            created_by=created_by,
        )
    except (TypeError, UploadValidationError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return output.result
