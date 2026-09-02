from __future__ import annotations

import asyncio
import typing
from datetime import date
from types import SimpleNamespace

import pytest

from ntk.agents.assessment_agent import AssessmentGenerationTimeoutError
from ntk.controllers.assessment.generation import (
    AssessmentGenerationOptions,
    AssessmentGenerationResult,
    GeneratedResidentAssessment,
    ResidentAssessmentGenerationOptions,
)
from ntk.controllers.assessment.import_assessments import AssessmentImportResult
from ntk.controllers.assessment.sync import AssessmentSyncOptions
from ntk.controllers.assessment.update import (
    AssessmentUpdateOptions,
    AssessmentUpdateRequest,
)
from ntk.models.sql.resident import ResidentAssessment
from ntk.presentation.api.routers import assessments
from ntk.services.assessment import AssessmentSyncResult

if typing.TYPE_CHECKING:
    from ntk.controllers.assessment.finalize import AssessmentFinalizeOptions
    from ntk.controllers.assessment.get import AssessmentGetOptions


class Upload:
    filename = "assessment.pdf"

    async def read(self) -> bytes:
        return b"pdf"


def test_get_route_returns_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = ResidentAssessment(
        id=1,
        resident_id=1,
        content="Assessment",
        content_hash="hash",
        assessment_date=date(2026, 8, 31),
        created_by="model",
    )

    class Controller:
        def __init__(self, session: object) -> None:
            assert session == "session"

        def run(self, options: AssessmentGetOptions) -> object:
            assert options.assessment_id == assessment.id
            return SimpleNamespace(result=SimpleNamespace(assessment=assessment))

    monkeypatch.setattr(assessments, "AssessmentGetCommandController", Controller)

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
    assessment = ResidentAssessment(
        id=1,
        resident_id=1,
        content="Assessment",
        content_hash="hash",
        assessment_date=date(2026, 8, 31),
        created_by="model",
    )

    class Controller:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        def run(_options: object) -> object:
            return SimpleNamespace(
                result=SimpleNamespace(assessments=[assessment]),
            )

    monkeypatch.setattr(assessments, "AssessmentListController", Controller)

    assert asyncio.run(
        assessments.list_assessments("session"),  # ty: ignore[invalid-argument-type]
    ) == [assessment]


def test_update_route_passes_patch_to_controller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assessment = ResidentAssessment(
        id=1,
        resident_id=1,
        content="Updated",
        content_hash="hash",
        assessment_date=date(2026, 8, 31),
        created_by="dietitian",
    )

    class Controller:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        async def run(options: AssessmentUpdateOptions) -> object:
            assert options.assessment_id == assessment.id
            assert options.content == "Updated"
            return SimpleNamespace(result=assessment)

    monkeypatch.setattr(assessments, "AssessmentUpdateController", Controller)

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
    assessment = ResidentAssessment(
        id=1,
        resident_id=1,
        content="Assessment",
        content_hash="hash",
        assessment_date=date(2026, 8, 31),
        created_by="model",
    )

    class Controller:
        def __init__(self, session: object) -> None:
            assert session == "session"

        async def run(self, options: AssessmentFinalizeOptions) -> object:
            assert options.assessment_id == assessment.id
            return SimpleNamespace(result=assessment)

    monkeypatch.setattr(assessments, "AssessmentFinalizeController", Controller)

    result = asyncio.run(
        assessments.finalize_assessment(
            1,
            "session",  # ty: ignore[invalid-argument-type]
        ),
    )

    assert result is assessment


def test_generate_route_passes_resident_specific_contexts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resident_id = 1
    assessment = ResidentAssessment(
        resident_id=resident_id,
        content="Assessment",
        content_hash="hash",
        assessment_date=date(2026, 8, 30),
        created_by="model",
    )
    generated_assessment = GeneratedResidentAssessment(
        **assessment.model_dump(),
        resident_name="Resident One",
    )

    class Controller:
        def __init__(self, session: object) -> None:
            assert session == "session"

        async def run(self, options: AssessmentGenerationOptions) -> object:
            assert options.residents == [
                ResidentAssessmentGenerationOptions(
                    resident_identifier="R-1",
                    facility_id="FAC-1",
                    context="wound healing",
                ),
                ResidentAssessmentGenerationOptions(
                    resident_identifier="R-2",
                    facility_id="FAC-2",
                    context="renal nutrition",
                ),
            ]
            return SimpleNamespace(
                result=AssessmentGenerationResult(
                    assessments=[generated_assessment],
                ),
            )

    monkeypatch.setattr(assessments, "AssessmentGenerationController", Controller)

    result = asyncio.run(
        assessments.generate_assessments(
            AssessmentGenerationOptions(
                residents=[
                    ResidentAssessmentGenerationOptions(
                        resident_identifier="R-1",
                        facility_id="FAC-1",
                        context="wound healing",
                    ),
                    ResidentAssessmentGenerationOptions(
                        resident_identifier="R-2",
                        facility_id="FAC-2",
                        context="renal nutrition",
                    ),
                ],
            ),
            "session",  # ty: ignore[invalid-argument-type]
        ),
    )

    assert result == [generated_assessment]
    assert result[0].resident_name == "Resident One"


def test_generate_route_returns_not_found_for_unknown_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Controller:
        def __init__(self, _session: object) -> None:
            pass

        @staticmethod
        async def run(_options: AssessmentGenerationOptions) -> object:
            message = "Resident 'UNKNOWN' was not found"
            raise LookupError(message)

    monkeypatch.setattr(assessments, "AssessmentGenerationController", Controller)

    with pytest.raises(assessments.HTTPException) as error:
        asyncio.run(
            assessments.generate_assessments(
                AssessmentGenerationOptions(
                    residents=[
                        ResidentAssessmentGenerationOptions(
                            resident_identifier="UNKNOWN",
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
    class Controller:
        def __init__(self, _session: object) -> None:
            pass

        @staticmethod
        async def run(_options: AssessmentGenerationOptions) -> object:
            message = "Assessment generation timed out after 180 seconds"
            raise AssessmentGenerationTimeoutError(message)

    monkeypatch.setattr(assessments, "AssessmentGenerationController", Controller)

    with pytest.raises(assessments.HTTPException) as error:
        asyncio.run(
            assessments.generate_assessments(
                AssessmentGenerationOptions(
                    residents=[
                        ResidentAssessmentGenerationOptions(
                            resident_identifier="R-1",
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

    class Controller:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        async def run(options: AssessmentSyncOptions) -> object:
            assert options == AssessmentSyncOptions()
            return SimpleNamespace(result=expected)

    monkeypatch.setattr(assessments, "AssessmentSyncController", Controller)

    result = asyncio.run(
        assessments.sync_assessments(
            "session",  # ty: ignore[invalid-argument-type]
        ),
    )

    assert result is expected


def test_import_route_passes_one_file_to_controller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = AssessmentImportResult(assessments=[])

    class Controller:
        def __init__(self, session: object) -> None:
            assert session == "session"

        async def run_upload(
            self,
            file: Upload,
            *,
            overwrite: bool,
            created_by: str,
        ) -> object:
            assert file.filename == "assessment.pdf"
            assert overwrite is True
            assert created_by == "dietitian"
            return SimpleNamespace(result=expected)

    monkeypatch.setattr(assessments, "AssessmentImportController", Controller)

    result = asyncio.run(
        assessments.import_assessments(
            Upload(),  # ty: ignore[invalid-argument-type]
            overwrite=True,
            created_by="dietitian",
            session="session",  # ty: ignore[invalid-argument-type]
        ),
    )

    assert result is expected
