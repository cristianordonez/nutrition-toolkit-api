"""FastAPI routes for semantic vector search."""

from __future__ import annotations

import typing

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session  # noqa: TC002

from ntk.controllers.search.assessment import (
    AssessmentSearchController,
    AssessmentSearchOptions,
)
from ntk.controllers.search.knowledge import (
    KnowledgeSearchOptions,
    KnowledgeVectorSearchController,
)
from ntk.database.db import get_session
from ntk.defaults import (
    ADMIN_PERMISSION,
    ASSESSMENTS_READ_PERMISSION,
    KNOWLEDGE_READ_PERMISSION,
)
from ntk.models.rag import RagSearchMatch
from ntk.presentation.api.middleware import rate_limit, require_any_permission

router = APIRouter()


@router.post(
    "/search/knowledge",
    response_model=list[RagSearchMatch],
    dependencies=[
        Depends(
            require_any_permission([ADMIN_PERMISSION, KNOWLEDGE_READ_PERMISSION]),
        ),
        Depends(rate_limit(60, window=3600, scope="search-knowledge")),
    ],
)
async def search_knowledge(
    options: KnowledgeSearchOptions,
    session: typing.Annotated[Session, Depends(get_session)],
) -> list[RagSearchMatch]:
    """Return knowledge chunks closest to the supplied query."""
    try:
        output = KnowledgeVectorSearchController(session).run(options)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return output.result.matches


@router.post(
    "/search/assessments",
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
        output = AssessmentSearchController(session).run(options)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return output.result.matches
