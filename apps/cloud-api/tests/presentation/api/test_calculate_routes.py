from __future__ import annotations

import asyncio

from api.controllers.calculate.energy import EnergyOptions, EnergyResponse
from api.presentation.api.main import app
from api.presentation.api.routers.calculate import calculate_energy


def test_energy_route_uses_controller() -> None:
    result = asyncio.run(
        calculate_energy(
            EnergyOptions(
                weight=180,
                height=70,
                age=45,
            ),
        ),
    )

    assert isinstance(result, EnergyResponse)


def test_calculator_routes_accept_browser_compatible_post_requests() -> None:
    paths = app.openapi()["paths"]

    assert "get" in paths["/api/v1/calculate/"]
    assert "post" in paths["/api/v1/calculate/"]
    assert "/api/v1/calculate/tubefeed" not in paths
