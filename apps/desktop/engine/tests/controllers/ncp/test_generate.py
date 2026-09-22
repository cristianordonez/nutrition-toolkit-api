from __future__ import annotations

import asyncio
import typing
from datetime import UTC, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

from engine.controllers.ncp import generate as generate_module
from engine.controllers.ncp.generate import (
    NCPGenerateController,
    NCPGenerateOptions,
)
from engine.models.sql.person import Person
from engine.repositories.person_repo import PersonRepo
from ntk.models.ncp_public import NutritionCareProcessPublic

if typing.TYPE_CHECKING:
    from ntk.models.ncp_context import NCPGenerationRequest


class _Agent:
    """Stands in for the on-device note agent, capturing its request."""

    def __init__(self) -> None:
        self.requests: list[NCPGenerationRequest] = []

    async def run(self, request: NCPGenerationRequest) -> str:
        self.requests.append(request)
        return "Nutrition Follow Up\nRes is a ..."


class _Client:
    """Stands in for cloud-api, capturing the request it was posted."""

    def __init__(self) -> None:
        self.requests: list[NCPGenerationRequest] = []

    async def generate_ncp(
        self,
        request: NCPGenerationRequest,
    ) -> NutritionCareProcessPublic:
        self.requests.append(request)
        return NutritionCareProcessPublic(
            id=31,
            person_identifier=request.person_identifier,
            note_text="Nutrition Follow Up\nFrom cloud-api ...",
            content_hash="hash",
            created_by="model",
            status="draft",
            created_at=datetime(2026, 9, 21, tzinfo=UTC),
        )


def _session_with_person() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    PersonRepo(session).create(
        Person(name="Cai, Test", person_identifier="EN140472"),
    )
    session.commit()
    return session


def test_generate_builds_the_request_and_returns_the_note() -> None:
    session = _session_with_person()
    agent = _Agent()
    controller = NCPGenerateController(
        session=session,
        agent=agent,  # ty: ignore[invalid-argument-type]
    )

    output = asyncio.run(
        controller.run(
            NCPGenerateOptions(person_id=1, additional_context="wound review"),
        ),
    )

    assert len(agent.requests) == 1
    request = agent.requests[0]
    assert request.person_identifier == "EN140472"
    assert request.person.name == "Cai, Test"
    assert request.additional_context == "wound review"
    assert output.exit_code == 0
    assert output.result.note_text.startswith("Nutrition Follow Up")
    assert output.result.person_identifier == "EN140472"
    assert output.result.generated_by == "local"


def test_generate_rejects_a_person_without_an_identifier() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    PersonRepo(session).create(Person(name="No Identifier"))
    session.commit()
    agent = _Agent()
    controller = NCPGenerateController(
        session=session,
        agent=agent,  # ty: ignore[invalid-argument-type]
    )

    with pytest.raises(ValueError, match="person identifier is required"):
        asyncio.run(controller.run(NCPGenerateOptions(person_id=1)))

    assert agent.requests == []


def test_generation_goes_to_cloud_api_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generation belongs cloud-side; local is only an explicit escape hatch."""
    # Pinned rather than inherited: a developer's .env must not decide what
    # this asserts.
    monkeypatch.setattr(generate_module.SETTINGS, "use_local_generation", False)
    session = _session_with_person()
    client = _Client()
    controller = NCPGenerateController(
        session=session,
        client=client,  # ty: ignore[invalid-argument-type]
    )

    output = asyncio.run(controller.run(NCPGenerateOptions(person_id=1)))

    assert len(client.requests) == 1
    assert client.requests[0].person_identifier == "EN140472"
    assert output.result.generated_by == "cloud-api"
    assert "From cloud-api" in output.result.note_text
