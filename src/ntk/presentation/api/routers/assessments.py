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
from ntk.controllers.assessment.generate import (
    AssessmentGenerationOptions,
    AssessmentGenerationResult,
    GeneratedPersonAssessment,
)
from ntk.controllers.assessment.import_assessments import (
    AssessmentImportController,
    AssessmentImportResult,
)
from ntk.controllers.assessment.search import (
    AssessmentSearchOptions,  # noqa: TC001 - FastAPI evaluates annotations
)
from ntk.controllers.assessment.update import (
    AssessmentUpdateRequest,  # noqa: TC001 - FastAPI evaluates annotations
)
from ntk.database.db import get_session
from ntk.defaults import (
    ADMIN_PERMISSION,
    ASSESSMENTS_READ_PERMISSION,
    ASSESSMENTS_WRITE_PERMISSION,
)
from ntk.models.rag import RagSearchMatch
from ntk.models.sql.person import PersonAssessment
from ntk.pipelines.assessment import (
    AssessmentPipeline,
    AssessmentSyncResult,
)
from ntk.presentation.api.middleware import rate_limit, require_any_permission
from ntk.repositories.assessment_repo import AssessmentRepo
from ntk.repositories.embedding_repo import EmbeddingRepo
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.food_repo import FoodRepo
from ntk.repositories.person_repo import PersonRepo
from ntk.repositories.progress_note_repo import ProgressNoteRepo
from ntk.services.assessment_service import AssessmentService
from ntk.services.calculators.tubefeed_calculator import TubeFeedCalculator
from ntk.services.embedding_service import EmbeddingService
from ntk.services.facility_resolver import FacilityResolver
from ntk.services.person.detail_builder import PersonDetailBuilder
from ntk.services.person.person_service import PersonService

router = APIRouter()


def _require_assessment(
    assessment: PersonAssessment | None,
    assessment_id: int,
) -> PersonAssessment:
    """Return an assessment or raise the shared not-found error."""
    if assessment is None:
        message = f"Assessment {assessment_id} was not found"
        raise LookupError(message)
    return assessment


@router.get(
    "/assessments",
    response_model=list[PersonAssessment],
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
) -> list[PersonAssessment]:
    """Return all person assessments."""
    return AssessmentService(AssessmentRepo(session)).list_assessments()


@router.get(
    "/assessments/{assessment_id}",
    response_model=PersonAssessment,
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
) -> PersonAssessment:
    """Return one person assessment by ID."""
    try:
        assessment = _require_assessment(
            AssessmentService(AssessmentRepo(session)).get(assessment_id),
            assessment_id,
        )
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    return assessment


@router.patch(
    "/assessments/{assessment_id}",
    response_model=PersonAssessment,
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
) -> PersonAssessment:
    """Update editable fields on one person assessment."""
    try:
        assessment = _require_assessment(
            await AssessmentPipeline(AssessmentRepo(session)).update(
                assessment_id,
                **request.model_dump(),
            ),
            assessment_id,
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
    return assessment


@router.post(
    "/assessments/{assessment_id}/finalize",
    response_model=PersonAssessment,
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
) -> PersonAssessment:
    """Mark one person assessment as finalized."""
    try:
        assessment = _require_assessment(
            await AssessmentPipeline(AssessmentRepo(session)).finalize(assessment_id),
            assessment_id,
        )
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    return assessment


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
    return await AssessmentPipeline(
        AssessmentRepo(session),
        progress_note_repository=ProgressNoteRepo(session),
    ).sync_assessments()


@router.post(
    "/assessments/generate",
    response_model=list[GeneratedPersonAssessment],
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
) -> list[GeneratedPersonAssessment]:
    """Generate assessments from external person identifiers and context."""
    try:
        facility_resolver = FacilityResolver(FacilityRepo(session))
        food_repository = FoodRepo(session)
        assessments = await AssessmentPipeline(
            AssessmentRepo(session),
            person_service=PersonService(
                PersonRepo(session),
                facility_resolver,
                PersonDetailBuilder(TubeFeedCalculator(food_repository)),
            ),
            embedding_repository=EmbeddingRepo(session),
            food_repository=food_repository,
        ).generate_many(options.persons)
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
    return AssessmentGenerationResult.from_assessments(assessments).assessments


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
    files: typing.Annotated[
        list[UploadFile],
        File(description="One or more PCC progress-note report PDFs"),
    ],
    session: typing.Annotated[Session, Depends(get_session)],
    *,
    overwrite: typing.Annotated[bool, Form()] = False,
    created_by: typing.Annotated[str | None, Form()] = None,
) -> AssessmentImportResult:
    """Import nutrition notes from multiple PCC progress-note reports."""
    try:
        output = await AssessmentImportController(session).run_uploads(
            files,
            overwrite=overwrite,
            created_by=created_by,
        )
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return output.result


@router.post(
    "/assessments/search",
    response_model=list[RagSearchMatch],
    dependencies=[
        Depends(
            require_any_permission([ADMIN_PERMISSION, ASSESSMENTS_READ_PERMISSION]),
        ),
        Depends(rate_limit(60, window=3600, scope="search-assessments")),
    ],
)
async def search_assessments(
    options: AssessmentSearchOptions,
    session: typing.Annotated[Session, Depends(get_session)],
) -> list[RagSearchMatch]:
    """Return assessments closest to the supplied query."""
    try:
        matches = await EmbeddingService(
            EmbeddingRepo(session),
        ).search_assessments_async(
            options.text,
            options.top_k,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return matches
