"""FastAPI routes for knowledge ingestion and search."""

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

from ntk.controllers.knowledge.ingest import KnowledgeIngestController
from ntk.controllers.uploads import UploadValidationError
from ntk.database.db import get_session
from ntk.defaults import (
    ADMIN_PERMISSION,
    KNOWLEDGE_WRITE_PERMISSION,
)
from ntk.models.knowledge import KnowledgeIngestResponsePublic, KnowledgeType
from ntk.presentation.api.middleware import rate_limit, require_any_permission

router = APIRouter()


@router.post(
    "/knowledge/ingest",
    response_model=KnowledgeIngestResponsePublic,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, KNOWLEDGE_WRITE_PERMISSION],
            ),
        ),
        Depends(rate_limit(50, window=3600, scope="knowledge-ingest")),
    ],
)
async def ingest_pdfs(
    files: typing.Annotated[
        list[UploadFile],
        File(description="One or more PDF or text files"),
    ],
    document_type: typing.Annotated[
        KnowledgeType,
        Form(description="Document category"),
    ],
    *,
    overwrite: typing.Annotated[
        bool,
        Form(description="Replace and re-embed an existing document"),
    ] = False,
    session: typing.Annotated[Session | None, Depends(get_session)] = None,
) -> KnowledgeIngestResponsePublic:
    """Ingest one or more clinical knowledge documents."""
    try:
        output = await KnowledgeIngestController(session).run_uploads(
            files,
            document_type,
            overwrite=overwrite,
        )
    except UploadValidationError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(err),
        ) from err
    return output.result
