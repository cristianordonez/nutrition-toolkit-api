from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from ntk.agents.assessment_agent import AssessmentGenerationTimeoutError
from ntk.controllers.assessment.generate import (
    AssessmentGenerationOptions,
    PersonAssessmentGenerationOptions,
)
from ntk.controllers.assessment.import_assessments import AssessmentImportResult
from ntk.controllers.assessment.update import AssessmentUpdateRequest
from ntk.models.sql.person import Person, PersonAssessment
from ntk.pipelines.assessment import AssessmentSyncResult
from ntk.presentation.api.routers import assessments


class Upload:
    filename = "assessment.pdf"

    async def read(self) -> bytes:
        return b"pdf"


def test_get_route_returns_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = PersonAssessment(
        id=1,
        person_id=1,
        content="Assessment",
        content_hash="hash",
        assessment_date=date(2026, 8, 31),
        created_by="model",
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Service:
        def __init__(self, repository: Repository) -> None:
            assert isinstance(repository, Repository)

        @staticmethod
        def get(assessment_id: int) -> PersonAssessment:
            assert assessment_id == assessment.id
            return assessment

    monkeypatch.setattr(assessments, "AssessmentRepo", Repository)
    monkeypatch.setattr(assessments, "AssessmentService", Service)

    result = asyncio.run(
        assessments.get_assessment(
            1,
            "session",  # ty: ignore[invalid-argument-type]
        ),
    )

    assert result is assessment


def test_list_route_returns_assessments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = PersonAssessment(
        id=1,
        person_id=1,
        content="Assessment",
        content_hash="hash",
        assessment_date=date(2026, 8, 31),
        created_by="model",
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Service:
        def __init__(self, repository: Repository) -> None:
            assert isinstance(repository, Repository)

        @staticmethod
        def list_assessments() -> list[PersonAssessment]:
            return [assessment]

    monkeypatch.setattr(assessments, "AssessmentRepo", Repository)
    monkeypatch.setattr(assessments, "AssessmentService", Service)

    assert asyncio.run(
        assessments.list_assessments("session"),  # ty: ignore[invalid-argument-type]
    ) == [assessment]


def test_update_route_passes_patch_to_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = PersonAssessment(
        id=1,
        person_id=1,
        content="Updated",
        content_hash="hash",
        assessment_date=date(2026, 8, 31),
        created_by="dietitian",
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Pipeline:
        def __init__(self, repository: Repository) -> None:
            assert isinstance(repository, Repository)

        @staticmethod
        async def update(assessment_id: int, **updates: object) -> PersonAssessment:
            assert assessment_id == assessment.id
            assert updates["content"] == "Updated"
            return assessment

    monkeypatch.setattr(assessments, "AssessmentRepo", Repository)
    monkeypatch.setattr(assessments, "AssessmentPipeline", Pipeline)

    result = asyncio.run(
        assessments.update_assessment(
            1,
            AssessmentUpdateRequest(content="Updated"),
            "session",  # ty: ignore[invalid-argument-type]
        ),
    )

    assert result is assessment


def test_finalize_route_returns_updated_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = PersonAssessment(
        id=1,
        person_id=1,
        content="Assessment",
        content_hash="hash",
        assessment_date=date(2026, 8, 31),
        created_by="model",
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Pipeline:
        def __init__(self, repository: Repository) -> None:
            assert isinstance(repository, Repository)

        @staticmethod
        async def finalize(assessment_id: int) -> PersonAssessment:
            assert assessment_id == assessment.id
            return assessment

    monkeypatch.setattr(assessments, "AssessmentRepo", Repository)
    monkeypatch.setattr(assessments, "AssessmentPipeline", Pipeline)

    result = asyncio.run(
        assessments.finalize_assessment(
            1,
            "session",  # ty: ignore[invalid-argument-type]
        ),
    )

    assert result is assessment


def test_generate_route_passes_person_specific_contexts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    person_id = 1
    person = Person(id=person_id, name="Person One")
    assessment = PersonAssessment(
        person_id=person_id,
        person=person,
        content="Assessment",
        content_hash="hash",
        assessment_date=date(2026, 8, 30),
        created_by="model",
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Pipeline:
        def __init__(self, *_repositories: object, **_dependencies: object) -> None:
            pass

        @staticmethod
        async def generate_many(requests: object) -> list[PersonAssessment]:
            assert requests == [
                PersonAssessmentGenerationOptions(
                    source_person_identifier="R-1",
                    facility_identifier="FAC-1",
                    context="wound healing",
                ),
                PersonAssessmentGenerationOptions(
                    source_person_identifier="R-2",
                    facility_identifier="FAC-2",
                    context="renal nutrition",
                ),
            ]
            return [assessment]

    monkeypatch.setattr(assessments, "AssessmentRepo", Repository)
    monkeypatch.setattr(assessments, "PersonRepo", Repository)
    monkeypatch.setattr(assessments, "EmbeddingRepo", Repository)
    monkeypatch.setattr(assessments, "FoodRepo", Repository)
    monkeypatch.setattr(assessments, "AssessmentPipeline", Pipeline)

    result = asyncio.run(
        assessments.generate_assessments(
            AssessmentGenerationOptions(
                persons=[
                    PersonAssessmentGenerationOptions(
                        source_person_identifier="R-1",
                        facility_identifier="FAC-1",
                        context="wound healing",
                    ),
                    PersonAssessmentGenerationOptions(
                        source_person_identifier="R-2",
                        facility_identifier="FAC-2",
                        context="renal nutrition",
                    ),
                ],
            ),
            "session",  # ty: ignore[invalid-argument-type]
        ),
    )

    assert len(result) == 1
    assert result[0].person_name == "Person One"


def test_generate_route_returns_not_found_for_unknown_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Repository:
        def __init__(self, _session: object) -> None:
            pass

    class Pipeline:
        def __init__(self, *_repositories: object, **_dependencies: object) -> None:
            pass

        @staticmethod
        async def generate_many(_requests: object) -> list[PersonAssessment]:
            message = "Person 'UNKNOWN' was not found"
            raise LookupError(message)

    monkeypatch.setattr(assessments, "AssessmentRepo", Repository)
    monkeypatch.setattr(assessments, "PersonRepo", Repository)
    monkeypatch.setattr(assessments, "EmbeddingRepo", Repository)
    monkeypatch.setattr(assessments, "FoodRepo", Repository)
    monkeypatch.setattr(assessments, "AssessmentPipeline", Pipeline)

    with pytest.raises(assessments.HTTPException) as error:
        asyncio.run(
            assessments.generate_assessments(
                AssessmentGenerationOptions(
                    persons=[
                        PersonAssessmentGenerationOptions(
                            source_person_identifier="UNKNOWN",
                        ),
                    ],
                ),
                "session",  # ty: ignore[invalid-argument-type]
            ),
        )

    assert error.value.status_code == 404  # noqa: PLR2004


def test_generate_route_returns_gateway_timeout_for_stalled_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Repository:
        def __init__(self, _session: object) -> None:
            pass

    class Pipeline:
        def __init__(self, *_repositories: object, **_dependencies: object) -> None:
            pass

        @staticmethod
        async def generate_many(_requests: object) -> list[PersonAssessment]:
            message = "Assessment generation timed out after 180 seconds"
            raise AssessmentGenerationTimeoutError(message)

    monkeypatch.setattr(assessments, "AssessmentRepo", Repository)
    monkeypatch.setattr(assessments, "PersonRepo", Repository)
    monkeypatch.setattr(assessments, "EmbeddingRepo", Repository)
    monkeypatch.setattr(assessments, "FoodRepo", Repository)
    monkeypatch.setattr(assessments, "AssessmentPipeline", Pipeline)

    with pytest.raises(assessments.HTTPException) as error:
        asyncio.run(
            assessments.generate_assessments(
                AssessmentGenerationOptions(
                    persons=[
                        PersonAssessmentGenerationOptions(
                            source_person_identifier="R-1",
                        ),
                    ],
                ),
                "session",  # ty: ignore[invalid-argument-type]
            ),
        )

    assert error.value.status_code == 504  # noqa: PLR2004
    assert error.value.detail == "Assessment generation timed out after 180 seconds"


def test_sync_route_returns_sync_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = AssessmentSyncResult(
        scanned=5,
        assessments_created=2,
        embeddings_created=2,
        skipped_not_nutrition=3,
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Pipeline:
        def __init__(
            self,
            repository: Repository,
            *,
            progress_note_repository: Repository,
        ) -> None:
            assert isinstance(repository, Repository)
            assert isinstance(progress_note_repository, Repository)

        @staticmethod
        async def sync_assessments() -> AssessmentSyncResult:
            return expected

    monkeypatch.setattr(assessments, "AssessmentRepo", Repository)
    monkeypatch.setattr(assessments, "ProgressNoteRepo", Repository)
    monkeypatch.setattr(assessments, "AssessmentPipeline", Pipeline)

    result = asyncio.run(
        assessments.sync_assessments(
            "session",  # ty: ignore[invalid-argument-type]
        ),
    )

    assert result is expected


def test_import_route_passes_multiple_files_to_controller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = AssessmentImportResult(assessments=[])

    class Controller:
        def __init__(self, session: object) -> None:
            assert session == "session"

        async def run_uploads(
            self,
            files: list[Upload],
            *,
            overwrite: bool,
            created_by: str,
        ) -> object:
            assert len(files) == 2  # noqa: PLR2004
            assert overwrite is True
            assert created_by == "dietitian"
            return SimpleNamespace(result=expected)

    monkeypatch.setattr(assessments, "AssessmentImportController", Controller)

    result = asyncio.run(
        assessments.import_assessments(
            [Upload(), Upload()],  # ty: ignore[invalid-argument-type]
            overwrite=True,
            created_by="dietitian",
            session="session",  # ty: ignore[invalid-argument-type]
        ),
    )

    assert result == expected
