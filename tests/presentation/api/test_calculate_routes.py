from __future__ import annotations

import asyncio

from sqlmodel import Session, SQLModel, create_engine

from ntk.controllers.tubefeed.calculate import (
    CalculateTubefeedOptions,
    CalculateTubefeedResponse,
)
from ntk.presentation.api.main import app
from ntk.presentation.api.routers.calculate import calculate_tubefeed
from ntk.repositories.food_repo import FoodRepo


def test_tubefeed_route_uses_controller() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        FoodRepo(session).seed_default_formulas()
        result = asyncio.run(
            calculate_tubefeed(
                CalculateTubefeedOptions(
                    energy_needs=(1800, 2000),
                    formula="jevity 1.5",
                    package_volume_ml=1000,
                ),
                session,
            ),
        )

    assert isinstance(result, CalculateTubefeedResponse)


def test_calculator_routes_accept_browser_compatible_post_requests() -> None:
    paths = app.openapi()["paths"]

    assert "get" in paths["/api/v1/calculate/"]
    assert "post" in paths["/api/v1/calculate/"]
    assert "get" in paths["/api/v1/calculate/tubefeed"]
    assert "post" in paths["/api/v1/calculate/tubefeed"]
