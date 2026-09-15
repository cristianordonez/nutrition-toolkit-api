"""FastAPI routes for Nutrition Care Process workflows."""

from __future__ import annotations

import typing

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlmodel import Session  # noqa: TC002

from api.agents.ncp_agent import NCPGenerationTimeoutError
from api.controllers.ncp.search import (
    NCPSearchOptions,  # noqa: TC001 - FastAPI evaluates annotations
)
from api.controllers.ncp.update import (
    NCPUpdateRequest,  # noqa: TC001 - FastAPI evaluates annotations
)
from api.database.db import get_session
from api.defaults import (
    ADMIN_PERMISSION,
    NCP_READ_PERMISSION,
    NCP_WRITE_PERMISSION,
)
from api.models.rag import RagSearchMatch
from api.models.sql.ncp import NutritionCareProcess
from api.pipelines.ncp import FinalizedNCPError, NutritionCareProcessPipeline
from api.presentation.api.middleware import rate_limit, require_any_permission
from api.repositories.embedding_repo import EmbeddingRepo
from api.repositories.ncp_repo import NCPRepo
from api.services.embedding_service import EmbeddingService
from api.services.ncp_service import NutritionCareProcessService
from ntk.models.ncp_context import NCPGenerationRequest  # noqa: TC001

router = APIRouter()


def _require_ncp(
    ncp: NutritionCareProcess | None,
    ncp_id: int,
) -> NutritionCareProcess:
    """Return an ncp or raise the shared not-found error."""
    if ncp is None:
        message = f"Nutrition Care Process {ncp_id} was not found"
        raise LookupError(message)
    return ncp


@router.get(
    "/nutrition-care-processes",
    response_model=list[NutritionCareProcess],
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, NCP_READ_PERMISSION],
            ),
        ),
        Depends(rate_limit(60, window=3600, scope="ncps-list")),
    ],
)
async def list_ncps(
    person_identifier: str,
    session: typing.Annotated[Session, Depends(get_session)],
) -> list[NutritionCareProcess]:
    """Return all Nutrition Care Processes for one person."""
    return NutritionCareProcessService(NCPRepo(session)).list_ncps(person_identifier)


@router.get(
    "/nutrition-care-processes/{ncp_id}",
    response_model=NutritionCareProcess,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, NCP_READ_PERMISSION],
            ),
        ),
        Depends(rate_limit(60, window=3600, scope="ncps-get")),
    ],
)
async def get_ncp(
    ncp_id: int,
    person_identifier: str,
    session: typing.Annotated[Session, Depends(get_session)],
) -> NutritionCareProcess:
    """Return one Nutrition Care Process by ID, scoped to its person."""
    try:
        ncp = _require_ncp(
            NutritionCareProcessService(NCPRepo(session)).get(
                ncp_id,
                person_identifier,
            ),
            ncp_id,
        )
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    return ncp


@router.patch(
    "/nutrition-care-processes/{ncp_id}",
    response_model=NutritionCareProcess,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, NCP_WRITE_PERMISSION],
            ),
        ),
        Depends(rate_limit(30, window=3600, scope="ncps-update")),
    ],
)
async def update_ncp(
    ncp_id: int,
    person_identifier: str,
    request: NCPUpdateRequest,
    session: typing.Annotated[Session, Depends(get_session)],
) -> NutritionCareProcess:
    """Update editable fields on one Nutrition Care Process."""
    try:
        ncp = _require_ncp(
            await NutritionCareProcessPipeline(
                NCPRepo(session),
            ).update(
                ncp_id,
                person_identifier,
                **request.model_dump(),
            ),
            ncp_id,
        )
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except FinalizedNCPError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return ncp


@router.post(
    "/nutrition-care-processes/{ncp_id}/finalize",
    response_model=NutritionCareProcess,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, NCP_WRITE_PERMISSION],
            ),
        ),
        Depends(rate_limit(30, window=3600, scope="ncps-finalize")),
    ],
)
async def finalize_ncp(
    ncp_id: int,
    person_identifier: str,
    session: typing.Annotated[Session, Depends(get_session)],
) -> NutritionCareProcess:
    """Mark one Nutrition Care Process as finalized."""
    try:
        ncp = _require_ncp(
            await NutritionCareProcessPipeline(
                NCPRepo(session),
            ).finalize(ncp_id, person_identifier),
            ncp_id,
        )
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    return ncp


@router.post(
    "/nutrition-care-processes/sync",
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, NCP_WRITE_PERMISSION],
            ),
        ),
        Depends(rate_limit(20, window=3600, scope="ncps-sync")),
    ],
)
async def sync_ncps(
    session: typing.Annotated[Session, Depends(get_session)],
) -> None:
    """Deferred: see the split refactor plan, decision 7.

    Always returns HTTP 501 -- NCP import/promotion has no coherent home now
    that generation/storage lives behind cloud-api's stateless HTTP boundary.
    """
    try:
        await NutritionCareProcessPipeline(NCPRepo(session)).sync_ncps()
    except NotImplementedError as error:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(error),
        ) from error


@router.post(
    "/nutrition-care-processes/generate",
    response_model=NutritionCareProcess,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, NCP_WRITE_PERMISSION],
            ),
        ),
        Depends(rate_limit(25, window=3600, scope="ncps-generate")),
    ],
)
async def generate_ncp(
    request: NCPGenerationRequest,
    session: typing.Annotated[Session, Depends(get_session)],
) -> NutritionCareProcess:
    """Generate and persist one Nutrition Care Process from a device-built context.

    The desktop engine assembles ``request`` entirely from data stored
    on-device; this endpoint never receives or persists raw person/clinical
    records, only the already-budgeted context and the generated result.
    """
    try:
        return await NutritionCareProcessPipeline(
            NCPRepo(session),
            embedding_repository=EmbeddingRepo(session),
        ).generate(request)
    except NCPGenerationTimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(error),
        ) from error


@router.post(
    "/nutrition-care-processes/search",
    response_model=list[RagSearchMatch],
    dependencies=[
        Depends(
            require_any_permission([ADMIN_PERMISSION, NCP_READ_PERMISSION]),
        ),
        Depends(rate_limit(60, window=3600, scope="search-ncps")),
    ],
)
async def search_ncps(
    options: NCPSearchOptions,
    session: typing.Annotated[Session, Depends(get_session)],
) -> list[RagSearchMatch]:
    """Return one person's ncps closest to the supplied query."""
    try:
        matches = await EmbeddingService(
            EmbeddingRepo(session),
        ).search_ncps_async(
            options.text,
            options.person_identifier,
            options.top_k,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return matches
