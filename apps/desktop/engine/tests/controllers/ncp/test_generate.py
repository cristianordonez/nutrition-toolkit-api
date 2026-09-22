from __future__ import annotations

import asyncio
import typing

import pytest
from sqlmodel import Session, SQLModel, create_engine

from engine.controllers.ncp.generate import (
    NCPGenerateController,
    NCPGenerateOptions,
)
from engine.models.sql.person import Person
from engine.repositories.person_repo import PersonRepo

if typing.TYPE_CHECKING:
    from ntk.models.ncp_context import NCPGenerationRequest


class _Agent:
    """Stands in for the on-device note agent, capturing its request."""

    def __init__(self) -> None:
        self.requests: list[NCPGenerationRequest] = []

    async def run(self, request: NCPGenerationRequest) -> str:
        self.requests.append(request)
        return "Nutrition Follow Up\nRes is a ..."


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
