from __future__ import annotations

import asyncio
import typing
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from ntk.models.sql.person import (
    ClinicalFactType,
    Person,
    PersonAssessment,
    PersonClinicalFact,
    PersonWeight,
)
from ntk.presentation.api.routers import persons

if typing.TYPE_CHECKING:
    from ntk.controllers.persons.assessments import PersonAssessmentsOptions
    from ntk.controllers.persons.clinical_facts import PersonClinicalFactsOptions
    from ntk.controllers.persons.weights import PersonWeightsOptions


def test_person_routes_use_request_scoped_controllers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    person = Person(
        id=1,
        person_id="R-1",
        name="Person",
        facility_id=1,
    )
    assessment = PersonAssessment(
        person_id=1,
        content="Assessment",
        content_hash="hash",
        assessment_date=date(2026, 8, 31),
        created_by="model",
    )
    weight = PersonWeight(
        person_id=1,
        measured_at=datetime(2026, 8, 31, tzinfo=UTC),
        weight_lb=150,
    )
    fact = PersonClinicalFact(
        person_id=1,
        clinical_fact_type=ClinicalFactType.OBSERVATION,
        observation_type="appetite",
        observed_at=datetime(2026, 8, 31, tzinfo=UTC),
    )

    class ListController:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        def run(_options: object) -> object:
            return SimpleNamespace(result=SimpleNamespace(persons=[person]))

    class AssessmentsController:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        def run(options: PersonAssessmentsOptions) -> object:
            assert options.person_ids == [person.id]
            return SimpleNamespace(result=SimpleNamespace(assessments=[assessment]))

    class WeightsController:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        def run(options: PersonWeightsOptions) -> object:
            assert options.person_ids == [person.id]
            return SimpleNamespace(result=SimpleNamespace(weights=[weight]))

    class FactsController:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        def run(options: PersonClinicalFactsOptions) -> object:
            assert options.person_ids == [person.id]
            return SimpleNamespace(result=SimpleNamespace(clinical_facts=[fact]))

    monkeypatch.setattr(persons, "PersonListController", ListController)
    monkeypatch.setattr(
        persons,
        "PersonAssessmentsController",
        AssessmentsController,
    )
    monkeypatch.setattr(persons, "PersonWeightsController", WeightsController)
    monkeypatch.setattr(
        persons,
        "PersonClinicalFactsController",
        FactsController,
    )

    assert asyncio.run(persons.list_persons("session")) == [person]  # ty: ignore[invalid-argument-type]
    assert asyncio.run(
        persons.get_person_assessments(person.id, "session"),  # ty: ignore[invalid-argument-type]
    ) == [assessment]
    assert asyncio.run(
        persons.get_person_weights(person.id, "session"),  # ty: ignore[invalid-argument-type]
    ) == [weight]
    assert asyncio.run(
        persons.get_person_clinical_facts(person.id, "session"),  # ty: ignore[invalid-argument-type]
    ) == [fact]


def test_get_person_detail_uses_person_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Service:
        def __init__(
            self,
            repository: Repository,
            *,
            person_detail_builder: object | None = None,
        ) -> None:
            assert isinstance(repository, Repository)
            assert person_detail_builder is not None

        @staticmethod
        def get_person_detail_by_id(person_id: int) -> object:
            assert person_id == 7  # noqa: PLR2004
            return SimpleNamespace(
                model_dump_json=lambda **_kwargs: '{"person_id":7}',
            )

    monkeypatch.setattr(persons, "PersonRepo", Repository)
    monkeypatch.setattr(persons, "PersonService", Service)

    response = asyncio.run(
        persons.get_person_detail(
            7,
            "session",  # ty: ignore[invalid-argument-type]
        ),
    )

    assert response.body == b'{"person_id":7}'


def test_get_person_detail_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Repository:
        def __init__(self, _session: object) -> None:
            pass

    class Service:
        def __init__(
            self,
            _repository: Repository,
            *,
            person_detail_builder: object | None = None,
        ) -> None:
            assert person_detail_builder is not None

        @staticmethod
        def get_person_detail_by_id(person_id: int) -> object:
            message = f"Person {person_id} was not found"
            raise LookupError(message)

    monkeypatch.setattr(persons, "PersonRepo", Repository)
    monkeypatch.setattr(persons, "PersonService", Service)

    with pytest.raises(persons.HTTPException) as error:
        asyncio.run(
            persons.get_person_detail(
                404,
                "session",  # ty: ignore[invalid-argument-type]
            ),
        )

    assert error.value.status_code == 404  # noqa: PLR2004
    assert error.value.detail == "Person 404 was not found"
