"""FastAPI routes for document ingestion."""

from __future__ import annotations

import typing

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from ntk.controllers.documents.ingest import (
    DocumentIngestController,
    DocumentIngestOptions,
)
from ntk.controllers.uploads import UploadValidationError
from ntk.defaults import ADMIN_PERMISSION, RESIDENTS_WRITE_PERMISSION
from ntk.presentation.api.middleware import rate_limit, require_any_permission
from ntk.services.resident_data.transform import ResidentTransformationResult

router = APIRouter()


@router.post(
    "/document/ingest",
    response_model=ResidentTransformationResult,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, RESIDENTS_WRITE_PERMISSION],
            ),
        ),
        Depends(rate_limit(40, window=3600, scope="document-ingest")),
    ],
)
async def ingest_documents(
    files: typing.Annotated[
        list[UploadFile],
        File(description="One or more PDF, CSV, or text documents"),
    ],
) -> ResidentTransformationResult:
    """Ingest all uploaded documents into the database."""
    try:
        output = await DocumentIngestController().run(
            DocumentIngestOptions(files=files),
        )
    except UploadValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return output.result
