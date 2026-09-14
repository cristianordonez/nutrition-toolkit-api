"""FastAPI routes for Nutrition Care Process workflows."""

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

from ntk.agents.ncp_agent import NCPGenerationTimeoutError
from ntk.controllers.ncp.generate import (
    GeneratedNCP,
    NCPGenerationOptions,
    NCPGenerationResult,
)
from ntk.controllers.ncp.import_ncps import (
    NCPImportController,
    NCPImportResult,
)
from ntk.controllers.ncp.search import (
    NCPSearchOptions,  # noqa: TC001 - FastAPI evaluates annotations
)
from ntk.controllers.ncp.update import (
    NCPUpdateRequest,  # noqa: TC001 - FastAPI evaluates annotations
)
from ntk.database.db import get_session
from ntk.defaults import (
    ADMIN_PERMISSION,
    NCP_READ_PERMISSION,
    NCP_WRITE_PERMISSION,
)
from ntk.models.rag import RagSearchMatch
from ntk.models.sql.person import PersonClinicalNote
from ntk.pipelines.ncp import (
    FinalizedNCPError,
    NCPSyncResult,
    NutritionCareProcessPipeline,
)
from ntk.presentation.api.middleware import rate_limit, require_any_permission
from ntk.repositories.clinical_note_repo import ClinicalNoteRepo
from ntk.repositories.embedding_repo import EmbeddingRepo
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.food_repo import FoodRepo
from ntk.repositories.person_repo import PersonRepo
from ntk.services.calculators.tubefeed_calculator import TubeFeedCalculator
from ntk.services.embedding_service import EmbeddingService
from ntk.services.facility_resolver import FacilityResolver
from ntk.services.ncp_service import NutritionCareProcessService
from ntk.services.person.detail_builder import PersonDetailBuilder
from ntk.services.person.person_service import PersonService

router = APIRouter()


def _require_ncp(
    ncp: PersonClinicalNote | None,
    ncp_id: int,
) -> PersonClinicalNote:
    """Return an ncp or raise the shared not-found error."""
    if ncp is None:
        message = f"Nutrition Care Process {ncp_id} was not found"
        raise LookupError(message)
    return ncp


@router.get(
    "/nutrition-care-processes",
    response_model=list[PersonClinicalNote],
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
    session: typing.Annotated[Session, Depends(get_session)],
) -> list[PersonClinicalNote]:
    """Return all Nutrition Care Processes."""
    return NutritionCareProcessService(ClinicalNoteRepo(session)).list_ncps()


@router.get(
    "/nutrition-care-processes/{ncp_id}",
    response_model=PersonClinicalNote,
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
    session: typing.Annotated[Session, Depends(get_session)],
) -> PersonClinicalNote:
    """Return one person ncp by ID."""
    try:
        ncp = _require_ncp(
            NutritionCareProcessService(ClinicalNoteRepo(session)).get(ncp_id),
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
    response_model=PersonClinicalNote,
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
    request: NCPUpdateRequest,
    session: typing.Annotated[Session, Depends(get_session)],
) -> PersonClinicalNote:
    """Update editable fields on one person ncp."""
    try:
        ncp = _require_ncp(
            await NutritionCareProcessPipeline(
                ClinicalNoteRepo(session),
            ).update(
                ncp_id,
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
    response_model=PersonClinicalNote,
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
    session: typing.Annotated[Session, Depends(get_session)],
) -> PersonClinicalNote:
    """Mark one person ncp as finalized."""
    try:
        ncp = _require_ncp(
            await NutritionCareProcessPipeline(
                ClinicalNoteRepo(session),
            ).finalize(ncp_id),
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
    response_model=NCPSyncResult,
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
) -> NCPSyncResult:
    """Synchronize historical Nutrition Care Processes and their embeddings."""
    return await NutritionCareProcessPipeline(
        ClinicalNoteRepo(session),
    ).sync_ncps()


@router.post(
    "/nutrition-care-processes/generate",
    response_model=list[GeneratedNCP],
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, NCP_WRITE_PERMISSION],
            ),
        ),
        Depends(rate_limit(25, window=3600, scope="ncps-generate")),
    ],
)
async def generate_ncps(
    options: NCPGenerationOptions,
    session: typing.Annotated[Session, Depends(get_session)],
) -> list[GeneratedNCP]:
    """Generate ncps from external person identifiers and context."""
    try:
        facility_resolver = FacilityResolver(FacilityRepo(session))
        food_repository = FoodRepo(session)
        ncps = await NutritionCareProcessPipeline(
            ClinicalNoteRepo(session),
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
    except NCPGenerationTimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(error),
        ) from error
    return NCPGenerationResult.from_ncps(ncps).ncps


@router.post(
    "/nutrition-care-processes/import",
    response_model=NCPImportResult,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, NCP_WRITE_PERMISSION],
            ),
        ),
        Depends(rate_limit(20, window=3600, scope="ncps-import")),
    ],
)
async def import_ncps(
    files: typing.Annotated[
        list[UploadFile],
        File(description="One or more PCC clinical-note report PDFs"),
    ],
    session: typing.Annotated[Session, Depends(get_session)],
    *,
    overwrite: typing.Annotated[bool, Form()] = False,
    created_by: typing.Annotated[str | None, Form()] = None,
) -> NCPImportResult:
    """Import nutrition notes from multiple PCC clinical-note reports."""
    try:
        output = await NCPImportController(session).run_uploads(
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
    """Return ncps closest to the supplied query."""
    try:
        matches = await EmbeddingService(
            EmbeddingRepo(session),
        ).search_ncps_async(
            options.text,
            options.top_k,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return matches
