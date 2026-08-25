from __future__ import annotations

import asyncio

from ntk.controllers.tubefeed.calculate import (
    CalculateTubefeedOptions,
    CalculateTubefeedResponse,
)
from ntk.presentation.api.routers.calculate import calculate_tubefeed


def test_tubefeed_route_uses_controller() -> None:
    result = asyncio.run(
        calculate_tubefeed(
            CalculateTubefeedOptions(
                energy_needs=(1800, 2000),
                formula="jevity",
            ),
        ),
    )

    assert isinstance(result, CalculateTubefeedResponse)
