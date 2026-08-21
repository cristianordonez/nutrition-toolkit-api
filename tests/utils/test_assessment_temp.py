# ruff: noqa: PYI034
from __future__ import annotations

from types import SimpleNamespace

import pytest

from ntk.models.document import StoredDocumentType
from ntk.utils.assessment_temp import (
    AssessmentService,
    PatientAssessmentData,
    RetrievedContext,
)


def _patient() -> PatientAssessmentData:
    return PatientAssessmentData.model_validate(
        {
            "demographics": {
                "age": 80,
                "sex": "female",
                "height_in": 60,
                "weight_lb": 120,
            },
            "weight_history": [],
            "diet": {
                "order": "regular",
                "texture": None,
                "liquid_consistency": None,
                "restrictions": [],
                "preferences": [],
            },
            "intake": {
                "meal_intake": None,
                "fluid_intake": None,
                "appetite": None,
                "assistance": None,
            },
            "labs": {"results": []},
            "medications": [],
            "diagnoses": [{"name": "diabetes", "code": None, "date": None}],
            "skin": {"wounds": [], "pressure_injuries": [], "notes": []},
            "edema": {"present": False, "locations": [], "severity": None},
            "tube_feeding": None,
            "supplements": [],
            "notes": [],
        },
    )


def _service() -> AssessmentService:
    service = object.__new__(AssessmentService)
    service.model = "test-model"
    return service


def test_assessment_calculations_and_default_query() -> None:
    patient = _patient()

    assert AssessmentService.calculate(patient) == {
        "height_cm": 152.4,
        "weight_kg": 54.4,
        "bmi": 23.4,
    }
    assert AssessmentService._query_for(patient) == (  # noqa: SLF001
        "Clinical nutrition guidance for diabetes, regular"
    )

    patient.demographics.height_in = None
    patient.demographics.weight_lb = None
    patient.diagnoses = []
    patient.diet.order = None
    assert AssessmentService.calculate(patient) == {}
    assert "Evidence-based" in AssessmentService._query_for(patient)  # noqa: SLF001


def test_extract_patient_data_returns_parsed_response() -> None:
    patient = _patient()
    service = _service()

    class Responses:
        def parse(self, **kwargs: object) -> object:
            assert kwargs["text_format"] is PatientAssessmentData
            return SimpleNamespace(output_parsed=patient)

    service.client = SimpleNamespace(responses=Responses())
    assert service.extract_patient_data([("patient.pdf", b"pdf")]) is patient


def test_extract_patient_data_rejects_empty_parsed_response() -> None:
    service = _service()
    responses = SimpleNamespace(
        parse=lambda **_: SimpleNamespace(output_parsed=None),
    )
    service.client = SimpleNamespace(responses=responses)

    with pytest.raises(RuntimeError, match="no structured patient data"):
        service.extract_patient_data([])


def test_search_and_generate_adime() -> None:
    service = _service()

    class Cursor:
        def __init__(self) -> None:
            self.parameters: tuple[object, ...] = ()

        def execute(self, _: str, parameters: tuple[object, ...]) -> None:
            self.parameters = parameters

        def fetchall(self) -> list[tuple[str, str, float]]:
            return [("manual.pdf", "guidance", 0.9)]

    cursor = Cursor()
    results = AssessmentService._search_document_type(  # noqa: SLF001
        cursor,  # ty: ignore[invalid-argument-type]
        "[0.1]",
        StoredDocumentType.NUTRITION_CARE_MANUAL,
        3,
    )
    assert results[0].filename == "manual.pdf"
    cursor_params = 3
    assert cursor.parameters[-1] == cursor_params

    class Responses:
        def create(self, **kwargs: object) -> object:
            assert "patient_data" in str(kwargs["input"])
            return SimpleNamespace(output_text="Completed ADIME")

    service.client = SimpleNamespace(responses=Responses())
    service.model = "model"
    service.master_prompt = "instructions"
    assert (
        service.generate_adime(_patient(), {}, results, [], None) == "Completed ADIME"
    )

    service.client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: SimpleNamespace(output_text="")),
    )
    with pytest.raises(RuntimeError, match="no completed assessment"):
        service.generate_adime(_patient(), {}, [], [], None)


def test_retrieve_context_queries_both_stored_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    service.open_ai_service = SimpleNamespace(create_embedding=lambda _: [0.1])
    seen: list[StoredDocumentType] = []

    class Cursor:
        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    class Connection:
        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def cursor(self) -> Cursor:
            return Cursor()

    def search(
        cursor: object,
        vector: str,
        document_type: StoredDocumentType,
        limit: int,
    ) -> list[RetrievedContext]:
        del cursor, vector, limit
        seen.append(document_type)
        return []

    monkeypatch.setattr(service, "_connect", lambda: Connection())  # noqa: PLW0108
    monkeypatch.setattr(service, "_search_document_type", search)

    assert service.retrieve_context("nutrition") == ([], [])
    assert seen == [
        StoredDocumentType.NUTRITION_CARE_MANUAL,
        StoredDocumentType.ASSESSMENT,
    ]
