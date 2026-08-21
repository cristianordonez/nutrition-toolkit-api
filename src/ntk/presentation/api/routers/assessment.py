"""Generate nutrition assessments from uploaded patient PDFs."""

from __future__ import annotations

import typing

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from ntk.utils.assessment_temp import AssessmentResponse, AssessmentService

router = APIRouter()
_ASSESSMENT_SERVICE = AssessmentService()


@router.post("/assessment/generate", response_model=AssessmentResponse)
async def generate_assessment(
    files: typing.Annotated[
        list[UploadFile],
        File(description="One or more patient PDF files"),
    ],
    query: typing.Annotated[
        str | None,
        Query(description="Optional retrieval query and assessment focus"),
    ] = None,
) -> AssessmentResponse:
    """Extract patient data, retrieve evidence, and generate an ADIME note."""
    if not files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="At least one PDF file is required",
        )

    uploaded_files: list[tuple[str, bytes]] = []
    for index, upload in enumerate(files):
        filename = upload.filename or f"patient-{index + 1}.pdf"
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"'{filename}' is not a PDF file",
            )
        data = await upload.read()
        if not data:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"'{filename}' is empty",
            )
        uploaded_files.append((filename, data))

    return _ASSESSMENT_SERVICE.create_assessment(uploaded_files, query)
