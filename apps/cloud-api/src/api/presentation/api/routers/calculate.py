"""FastAPI routes for nutrition calculations."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.controllers.calculate.energy import (
    EnergyController,
    EnergyOptions,
    EnergyResponse,
)
from api.defaults import ADMIN_PERMISSION, CALCULATE_READ_PERMISSION
from api.presentation.api.middleware import rate_limit, require_any_permission

router = APIRouter()


@router.post(
    "/calculate/",
    response_model=EnergyResponse,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, CALCULATE_READ_PERMISSION],
            ),
        ),
        Depends(rate_limit(120, window=3600, scope="calculate-energy")),
    ],
)
@router.get(
    "/calculate/",
    response_model=EnergyResponse,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, CALCULATE_READ_PERMISSION],
            ),
        ),
        Depends(rate_limit(120, window=3600, scope="calculate-energy")),
    ],
)
async def calculate_energy(
    options: EnergyOptions,
) -> EnergyResponse:
    """Calculate nutrition needs based on user metrics.

    :return: A dictionary containing the calculated energy needs.
    """
    return EnergyController().run(options).result
