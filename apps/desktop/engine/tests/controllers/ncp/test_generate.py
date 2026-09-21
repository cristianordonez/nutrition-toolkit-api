from __future__ import annotations

import asyncio
import typing
from datetime import UTC, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

from engine.controllers.ncp.generate import (
    NCPGenerateController,
    NCPGenerateOptions,
)
from engine.models.sql.person import Person
from engine.repositories.person_repo import PersonRepo
from ntk.models.ncp_public import NutritionCareProcessPublic

if typing.TYPE_CHECKING:
    from ntk.models.ncp_context import NCPGenerationRequest


def _generated(person_identifier: str) -> NutritionCareProcessPublic:
    return NutritionCareProcessPublic(
        id=31,
        person_identifier=person_identifier,
        note_text="Nutrition Follow Up\nRes is a ...",
        content_hash="hash",
        created_by="model",
        status="draft",
        created_at=datetime(2026, 9, 21, tzinfo=UTC),
    )


class _Client:
    """Stands in for cloud-api, capturing the request it was handed."""

    def __init__(self) -> None:
        self.requests: list[NCPGenerationRequest] = []

    async def generate_ncp(
        self,
        request: NCPGenerationRequest,
    ) -> NutritionCareProcessPublic:
        self.requests.append(request)
        return _generated(request.person_identifier)


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
    client = _Client()
    controller = NCPGenerateController(
        session=session,
        client=client,  # ty: ignore[invalid-argument-type]
    )

    output = asyncio.run(
        controller.run(
            NCPGenerateOptions(person_id=1, additional_context="wound review"),
        ),
    )

    assert len(client.requests) == 1
    request = client.requests[0]
    assert request.person_identifier == "EN140472"
    assert request.person.name == "Cai, Test"
    assert request.additional_context == "wound review"
    assert output.exit_code == 0
    assert output.result.ncp.note_text.startswith("Nutrition Follow Up")
    assert "EN140472" in output.result.to_console()


def test_generate_rejects_a_person_without_an_identifier() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    PersonRepo(session).create(Person(name="No Identifier"))
    session.commit()
    client = _Client()
    controller = NCPGenerateController(
        session=session,
        client=client,  # ty: ignore[invalid-argument-type]
    )

    with pytest.raises(ValueError, match="person identifier is required"):
        asyncio.run(controller.run(NCPGenerateOptions(person_id=1)))

    assert client.requests == []
