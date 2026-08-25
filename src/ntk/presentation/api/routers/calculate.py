"""FastAPI routes for nutrition calculations."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ntk.controllers.calculate.energy import (
    EnergyController,
    EnergyOptions,
    EnergyResponse,
)
from ntk.controllers.tubefeed.calculate import (
    CalculateTubefeedController,
    CalculateTubefeedOptions,
    CalculateTubefeedResponse,
)
from ntk.defaults import ADMIN_PERMISSION, CALCULATE_READ_PERMISSION
from ntk.presentation.api.middleware import rate_limit, require_any_permission

router = APIRouter()


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
    controller = EnergyController()
    output = controller.run(options)
    return output.result


@router.get(
    "/calculate/tubefeed",
    response_model=CalculateTubefeedResponse,
    dependencies=[
        Depends(
            require_any_permission(
                [ADMIN_PERMISSION, CALCULATE_READ_PERMISSION],
            ),
        ),
        Depends(rate_limit(120, window=3600, scope="calculate-tubefeed")),
    ],
)
async def calculate_tubefeed(
    options: CalculateTubefeedOptions,
) -> CalculateTubefeedResponse:
    """Calculate tubefeed energy needs.

    :return: A dictionary containing the calculated tubefeed energy needs.
    """
    return CalculateTubefeedController().run(options).result
