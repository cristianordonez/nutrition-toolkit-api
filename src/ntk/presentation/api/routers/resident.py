"""FastAPI routes for resident data extraction."""

from __future__ import annotations

import typing

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from ntk.controllers.resident.extract import (
    ResidentExtractController,
)
from ntk.controllers.uploads import UploadValidationError
from ntk.defaults import ADMIN_PERMISSION, RESIDENTS_READ_PERMISSION
from ntk.models.resident_data import ResidentContext
from ntk.presentation.api.middleware import rate_limit, require_any_permission

router = APIRouter()
_RESIDENT_EXTRACT_CONTROLLER = ResidentExtractController()


@router.post(
    "/resident/extract",
    response_model=ResidentContext,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, RESIDENTS_READ_PERMISSION],
            ),
        ),
        Depends(rate_limit(20, window=3600, scope="resident-extract")),
    ],
)
async def extract_resident_data(
    files: typing.Annotated[
        list[UploadFile],
        File(description="One or more resident PDF or CSV files"),
    ],
    context: typing.Annotated[
        str | None,
        Form(description="Optional resident facts or extraction guidance"),
    ] = None,
) -> ResidentContext:
    """Extract one structured resident record from uploaded PDF or CSV files."""
    try:
        output = await _RESIDENT_EXTRACT_CONTROLLER.run_uploads(files, context)
    except UploadValidationError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(err),
        ) from err
    return output.result
