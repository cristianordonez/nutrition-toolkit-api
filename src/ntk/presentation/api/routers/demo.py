"""FastAPI route for the end-to-end nutrition assessment demo."""

from __future__ import annotations

import typing

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic_ai.exceptions import ModelAPIError
from sqlmodel import Session  # noqa: TC002

from ntk.agents.assessment_agent import AssessmentGenerationTimeoutError
from ntk.controllers.demo import DemoAssessmentController, DemoAssessmentOptions
from ntk.database.db import get_session
from ntk.defaults import (
    ADMIN_PERMISSION,
    ASSESSMENTS_WRITE_PERMISSION,
    PERSONS_WRITE_PERMISSION,
)
from ntk.models.demo_assessment import DemoAssessmentResponse
from ntk.presentation.api.middleware import rate_limit, require_any_permission

router = APIRouter()


@router.post(
    "/demo/assessment",
    response_model=DemoAssessmentResponse,
    dependencies=[
        Depends(
            require_any_permission([ADMIN_PERMISSION, PERSONS_WRITE_PERMISSION]),
        ),
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, ASSESSMENTS_WRITE_PERMISSION],
            ),
        ),
        Depends(rate_limit(10, window=3600, scope="demo-assessment")),
    ],
)
async def generate_demo_assessment(
    files: typing.Annotated[
        list[UploadFile],
        File(description="Clinical PDF, CSV, or text documents for one person"),
    ],
    session: typing.Annotated[Session, Depends(get_session)],
) -> DemoAssessmentResponse:
    """Combine document facts and generate one assessment without persistence."""
    try:
        output = await DemoAssessmentController(session).run(
            DemoAssessmentOptions(files=files),
        )
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except AssessmentGenerationTimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(error),
        ) from error
    except (ConnectionError, ModelAPIError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI provider unavailable: {error}",
        ) from error
    return output.result


__all__ = ["generate_demo_assessment", "router"]
