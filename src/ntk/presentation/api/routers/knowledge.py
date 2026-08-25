"""FastAPI routes for knowledge ingestion and search."""

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

from ntk.controllers.knowledge.ingest import KnowledgeIngestController
from ntk.controllers.knowledge.search import KnowledgeSearchController
from ntk.controllers.uploads import UploadValidationError
from ntk.defaults import (
    ADMIN_PERMISSION,
    KNOWLEDGE_READ_PERMISSION,
    KNOWLEDGE_WRITE_PERMISSION,
)
from ntk.models.knowledge import KnowledgeIngestResponsePublic, KnowledgeType
from ntk.models.rag import RagSearchMatch
from ntk.presentation.api.middleware import rate_limit, require_any_permission

router = APIRouter()
_KNOWLEDGE_INGEST_CONTROLLER = KnowledgeIngestController()
_KNOWLEDGE_SEARCH_CONTROLLER = KnowledgeSearchController()


@router.get(
    "/knowledge/search",
    response_model=list[RagSearchMatch],
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, KNOWLEDGE_READ_PERMISSION],
            ),
        ),
        Depends(rate_limit(60, window=3600, scope="knowledge-search")),
    ],
)
async def search_documents(
    text: typing.Annotated[str, Query(description="Text to search for")],
    top_k: typing.Annotated[
        int,
        Query(description="Number of closest chunks to return (clamped to 1-20)"),
    ] = 5,
) -> list[RagSearchMatch]:
    """Return document chunks closest to the embedded query text."""
    try:
        output = _KNOWLEDGE_SEARCH_CONTROLLER.search(text, top_k)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(err),
        ) from err
    return output.result.matches


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
) -> KnowledgeIngestResponsePublic:
    """Ingest one or more clinical knowledge documents."""
    try:
        output = await _KNOWLEDGE_INGEST_CONTROLLER.run_uploads(
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
