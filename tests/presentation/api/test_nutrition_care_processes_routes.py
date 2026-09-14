from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from ntk.agents.ncp_agent import NCPGenerationTimeoutError
from ntk.controllers.ncp.generate import (
    NCPGenerationOptions,
    PersonNCPGenerationOptions,
)
from ntk.controllers.ncp.import_ncps import NCPImportResult
from ntk.controllers.ncp.update import NCPUpdateRequest
from ntk.models.sql.person import (
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
    Person,
    PersonClinicalNote,
)
from ntk.pipelines.ncp import FinalizedNCPError, NCPSyncResult
from ntk.presentation.api.routers import nutrition_care_processes


class Upload:
    filename = "assessment.pdf"

    async def read(self) -> bytes:
        return b"pdf"


def test_get_route_returns_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = PersonClinicalNote(
        id=1,
        person_id=1,
        note_text="Assessment",
        raw_text="Assessment",
        note_key="ncp-1",
        content_hash="hash",
        note_date=date(2026, 8, 31),
        created_by="model",
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Service:
        def __init__(self, repository: Repository) -> None:
            assert isinstance(repository, Repository)

        @staticmethod
        def get(ncp_id: int) -> PersonClinicalNote:
            assert ncp_id == assessment.id
            return assessment

    monkeypatch.setattr(
        nutrition_care_processes,
        "ClinicalNoteRepo",
        Repository,
    )
    monkeypatch.setattr(
        nutrition_care_processes,
        "NutritionCareProcessService",
        Service,
    )

    result = asyncio.run(
        nutrition_care_processes.get_ncp(
            1,
            "session",  # ty: ignore[invalid-argument-type]
        ),
    )

    assert result is assessment


def test_list_route_returns_assessments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = PersonClinicalNote(
        id=1,
        person_id=1,
        note_text="Assessment",
        raw_text="Assessment",
        note_key="ncp-1",
        content_hash="hash",
        note_date=date(2026, 8, 31),
        created_by="model",
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Service:
        def __init__(self, repository: Repository) -> None:
            assert isinstance(repository, Repository)

        @staticmethod
        def list_ncps() -> list[PersonClinicalNote]:
            return [assessment]

    monkeypatch.setattr(
        nutrition_care_processes,
        "ClinicalNoteRepo",
        Repository,
    )
    monkeypatch.setattr(
        nutrition_care_processes,
        "NutritionCareProcessService",
        Service,
    )

    assert asyncio.run(
        nutrition_care_processes.list_ncps("session"),  # ty: ignore[invalid-argument-type]
    ) == [assessment]


def test_update_route_passes_patch_to_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = PersonClinicalNote(
        id=1,
        person_id=1,
        note_text="Updated",
        raw_text="Updated",
        note_key="ncp-1",
        content_hash="hash",
        note_date=date(2026, 8, 31),
        created_by="dietitian",
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Pipeline:
        def __init__(self, repository: Repository) -> None:
            assert isinstance(repository, Repository)

        @staticmethod
        async def update(ncp_id: int, **updates: object) -> PersonClinicalNote:
            assert ncp_id == assessment.id
            assert updates["note_text"] == "Updated"
            return assessment

    monkeypatch.setattr(
        nutrition_care_processes,
        "ClinicalNoteRepo",
        Repository,
    )
    monkeypatch.setattr(
        nutrition_care_processes,
        "NutritionCareProcessPipeline",
        Pipeline,
    )

    result = asyncio.run(
        nutrition_care_processes.update_ncp(
            1,
            NCPUpdateRequest(note_text="Updated"),
            "session",  # ty: ignore[invalid-argument-type]
        ),
    )

    assert result is assessment


def test_update_route_returns_conflict_for_finalized_ncp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Pipeline:
        def __init__(self, repository: Repository) -> None:
            assert isinstance(repository, Repository)

        @staticmethod
        async def update(_ncp_id: int, **_updates: object) -> None:
            message = "Nutrition Care Process 1 is finalized and cannot be edited"
            raise FinalizedNCPError(message)

    monkeypatch.setattr(
        nutrition_care_processes,
        "ClinicalNoteRepo",
        Repository,
    )
    monkeypatch.setattr(
        nutrition_care_processes,
        "NutritionCareProcessPipeline",
        Pipeline,
    )

    with pytest.raises(nutrition_care_processes.HTTPException) as error:
        asyncio.run(
            nutrition_care_processes.update_ncp(
                1,
                NCPUpdateRequest(note_text="Replacement content"),
                "session",  # ty: ignore[invalid-argument-type]
            ),
        )

    assert error.value.status_code == 409  # noqa: PLR2004
    assert error.value.detail == (
        "Nutrition Care Process 1 is finalized and cannot be edited"
    )


def test_finalize_route_returns_updated_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = PersonClinicalNote(
        id=1,
        person_id=1,
        note_text="Assessment",
        raw_text="Assessment",
        note_key="ncp-1",
        content_hash="hash",
        note_date=date(2026, 8, 31),
        created_by="model",
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Pipeline:
        def __init__(self, repository: Repository) -> None:
            assert isinstance(repository, Repository)

        @staticmethod
        async def finalize(ncp_id: int) -> PersonClinicalNote:
            assert ncp_id == assessment.id
            return assessment

    monkeypatch.setattr(
        nutrition_care_processes,
        "ClinicalNoteRepo",
        Repository,
    )
    monkeypatch.setattr(
        nutrition_care_processes,
        "NutritionCareProcessPipeline",
        Pipeline,
    )

    result = asyncio.run(
        nutrition_care_processes.finalize_ncp(
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
    assessment = PersonClinicalNote(
        person_id=person_id,
        person=person,
        note_date=datetime(2026, 8, 30, tzinfo=UTC),
        note_type="Nutrition/Dietary",
        author="model",
        note_text="Assessment",
        raw_text="Assessment",
        note_key="generated-1",
        ncp_source=NutritionCareProcessSource.GENERATED,
        content_hash="hash",
        ncp_index=0,
        created_by="model",
        status=NutritionCareProcessStatus.DRAFT,
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Pipeline:
        def __init__(self, *_repositories: object, **_dependencies: object) -> None:
            pass

        @staticmethod
        async def generate_many(requests: object) -> list[PersonClinicalNote]:
            assert requests == [
                PersonNCPGenerationOptions(
                    source_person_identifier="R-1",
                    facility_identifier="FAC-1",
                    context="wound healing",
                ),
                PersonNCPGenerationOptions(
                    source_person_identifier="R-2",
                    facility_identifier="FAC-2",
                    context="renal nutrition",
                ),
            ]
            return [assessment]

    monkeypatch.setattr(
        nutrition_care_processes,
        "ClinicalNoteRepo",
        Repository,
    )
    monkeypatch.setattr(nutrition_care_processes, "PersonRepo", Repository)
    monkeypatch.setattr(nutrition_care_processes, "EmbeddingRepo", Repository)
    monkeypatch.setattr(nutrition_care_processes, "FoodRepo", Repository)
    monkeypatch.setattr(
        nutrition_care_processes,
        "NutritionCareProcessPipeline",
        Pipeline,
    )

    result = asyncio.run(
        nutrition_care_processes.generate_ncps(
            NCPGenerationOptions(
                persons=[
                    PersonNCPGenerationOptions(
                        source_person_identifier="R-1",
                        facility_identifier="FAC-1",
                        context="wound healing",
                    ),
                    PersonNCPGenerationOptions(
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
        async def generate_many(_requests: object) -> list[PersonClinicalNote]:
            message = "Person 'UNKNOWN' was not found"
            raise LookupError(message)

    monkeypatch.setattr(
        nutrition_care_processes,
        "ClinicalNoteRepo",
        Repository,
    )
    monkeypatch.setattr(nutrition_care_processes, "PersonRepo", Repository)
    monkeypatch.setattr(nutrition_care_processes, "EmbeddingRepo", Repository)
    monkeypatch.setattr(nutrition_care_processes, "FoodRepo", Repository)
    monkeypatch.setattr(
        nutrition_care_processes,
        "NutritionCareProcessPipeline",
        Pipeline,
    )

    with pytest.raises(nutrition_care_processes.HTTPException) as error:
        asyncio.run(
            nutrition_care_processes.generate_ncps(
                NCPGenerationOptions(
                    persons=[
                        PersonNCPGenerationOptions(
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
        async def generate_many(_requests: object) -> list[PersonClinicalNote]:
            message = "Assessment generation timed out after 180 seconds"
            raise NCPGenerationTimeoutError(message)

    monkeypatch.setattr(
        nutrition_care_processes,
        "ClinicalNoteRepo",
        Repository,
    )
    monkeypatch.setattr(nutrition_care_processes, "PersonRepo", Repository)
    monkeypatch.setattr(nutrition_care_processes, "EmbeddingRepo", Repository)
    monkeypatch.setattr(nutrition_care_processes, "FoodRepo", Repository)
    monkeypatch.setattr(
        nutrition_care_processes,
        "NutritionCareProcessPipeline",
        Pipeline,
    )

    with pytest.raises(nutrition_care_processes.HTTPException) as error:
        asyncio.run(
            nutrition_care_processes.generate_ncps(
                NCPGenerationOptions(
                    persons=[
                        PersonNCPGenerationOptions(
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
    expected = NCPSyncResult(
        scanned=5,
        ncps_created=2,
        embeddings_created=2,
        skipped_not_nutrition=3,
    )

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    class Pipeline:
        def __init__(
            self,
            clinical_note_repository: Repository,
        ) -> None:
            assert isinstance(clinical_note_repository, Repository)

        @staticmethod
        async def sync_ncps() -> NCPSyncResult:
            return expected

    monkeypatch.setattr(
        nutrition_care_processes,
        "ClinicalNoteRepo",
        Repository,
    )
    monkeypatch.setattr(
        nutrition_care_processes,
        "NutritionCareProcessPipeline",
        Pipeline,
    )

    result = asyncio.run(
        nutrition_care_processes.sync_ncps(
            "session",  # ty: ignore[invalid-argument-type]
        ),
    )

    assert result is expected


def test_import_route_passes_multiple_files_to_controller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = NCPImportResult(ncps=[])

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

    monkeypatch.setattr(nutrition_care_processes, "NCPImportController", Controller)

    result = asyncio.run(
        nutrition_care_processes.import_ncps(
            [Upload(), Upload()],  # ty: ignore[invalid-argument-type]
            overwrite=True,
            created_by="dietitian",
            session="session",  # ty: ignore[invalid-argument-type]
        ),
    )

    assert result == expected
