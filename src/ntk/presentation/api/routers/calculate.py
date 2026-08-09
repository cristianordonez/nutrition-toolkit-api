from __future__ import annotations

import typing

from fastapi import APIRouter, Depends

from ntk.controllers.calculate.energy import (
    EnergyController,
    EnergyOptions,
    EnergyResponse,
)
from ntk.presentation.api.middleware import require_any_permission

if typing.TYPE_CHECKING:
    from ntk.models.api_key import APIKey

router = APIRouter()


@router.get("/calculate/", response_model=EnergyResponse)
async def calculate_energy(
    options: EnergyOptions,
    _: typing.Annotated[
        APIKey,
        Depends(require_any_permission(["admin", "calculate_energy"])),
    ],
) -> EnergyResponse:
    """Calculate nutrition needs based on user metrics.

    :return: A dictionary containing the calculated energy needs.
    """
    controller = EnergyController()
    output = controller.run(options)
    return output.result


@router.get("/calculate/tubefeed")
async def calculate_tubefeed() -> dict[str, int]:
    """Calculate tubefeed energy needs.

    :return: A dictionary containing the calculated tubefeed energy needs.
    """
    return {"kcal": 500}
