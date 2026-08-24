"""FastAPI routes for nutrition assessment workflows."""

from __future__ import annotations

import typing

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from ntk.controllers.assessment.generate import GenerateController
from ntk.controllers.assessment.ingest import (
    AssessmentIngestController,
    AssessmentIngestResponse,
)
from ntk.controllers.assessment.search import AssessmentSearchController
from ntk.controllers.uploads import UploadValidationError
from ntk.defaults import (
    ADMIN_PERMISSION,
    ASSESSMENTS_READ_PERMISSION,
    ASSESSMENTS_WRITE_PERMISSION,
)
from ntk.models.rag import RagSearchMatch
from ntk.models.sql.assessment import Assessment
from ntk.presentation.api.middleware import rate_limit, require_any_permission

router = APIRouter()
_GENERATE_CONTROLLER = GenerateController()
_ASSESSMENT_INGEST_CONTROLLER = AssessmentIngestController()
_ASSESSMENT_SEARCH_CONTROLLER = AssessmentSearchController()


@router.post(
    "/assessment/generate",
    response_model=Assessment,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, ASSESSMENTS_WRITE_PERMISSION],
            ),
        ),
        Depends(rate_limit(10, window=3600, scope="assessment-generate")),
    ],
)
async def generate_assessment(
    files: typing.Annotated[
        list[UploadFile],
        File(description="One or more resident PDF or CSV files"),
    ],
    context: typing.Annotated[
        str | None,
        Query(description="Optional resident context and assessment focus"),
    ] = None,
) -> Assessment:
    """Generate a nutrition assessment from resident PDF or CSV files."""
    try:
        output = await _GENERATE_CONTROLLER.run_uploads(files, context)
    except UploadValidationError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(err),
        ) from err
    return output.result


@router.post(
    "/assessment/ingest",
    response_model=AssessmentIngestResponse,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, ASSESSMENTS_WRITE_PERMISSION],
            ),
        ),
        Depends(rate_limit(20, window=3600, scope="assessment-ingest")),
    ],
)
async def ingest_assessments(
    files: typing.Annotated[
        list[UploadFile],
        File(description="One or more completed assessment PDF or text files"),
    ],
) -> AssessmentIngestResponse:
    """Ingest completed assessments for retrieval."""
    try:
        output = await _ASSESSMENT_INGEST_CONTROLLER.run_uploads(
            files,
        )
    except UploadValidationError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(err),
        ) from err
    return output.result


@router.get(
    "/assessment/search",
    response_model=list[RagSearchMatch],
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, ASSESSMENTS_READ_PERMISSION],
            ),
        ),
        Depends(rate_limit(60, window=3600, scope="assessment-search")),
    ],
)
async def search_assessments(
    text: typing.Annotated[str, Query(description="Text to search for")],
    top_k: typing.Annotated[
        int,
        Query(description="Number of closest assessments to return", ge=1, le=20),
    ] = 5,
) -> list[RagSearchMatch]:
    """Return assessment chunks closest to the supplied text."""
    try:
        output = await _ASSESSMENT_SEARCH_CONTROLLER.search(text, top_k)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(err),
        ) from err
    return output.result.matches
