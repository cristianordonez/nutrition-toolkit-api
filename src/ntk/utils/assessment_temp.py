"""Temporary end-to-end implementation for generating a nutrition assessment."""

from __future__ import annotations

import base64
import json
import typing
from importlib import import_module
from pathlib import Path

from pydantic import BaseModel

from ntk.models.document import StoredDocumentType
from ntk.models.settings import SETTINGS
from ntk.services.open_ai_service import OpenAIService

if typing.TYPE_CHECKING:
    from psycopg import Connection, Cursor

ASSESSMENT_MODEL = "gpt-4.1"
DEFAULT_RETRIEVAL_QUERY = (
    "Evidence-based clinical nutrition guidance relevant to this patient's "
    "diagnoses, intake, weight history, labs, skin, and nutrition support"
)
_PROMPT_PATH = Path(__file__).resolve().parents[1] / "static" / "prompt.md"
_SEARCH_SQL = """
    SELECT d.filename, c.content,
           1 - (e.embedding_vector <=> %s::vector) AS similarity
    FROM document_embeddings e
    JOIN document_chunks c ON c.id = e.document_chunk_id
    JOIN document d ON d.id = c.document_id
    WHERE d.document_type = %s
    ORDER BY e.embedding_vector <=> %s::vector
    LIMIT %s
"""


class PatientDemographics(BaseModel):
    """Patient measurements and demographic facts found in the source files."""

    age: int | None
    sex: str | None
    height_in: float | None
    weight_lb: float | None


class WeightHistoryEntry(BaseModel):
    """One dated or described historical weight."""

    date: str | None
    weight_lb: float | None
    description: str | None


class DietData(BaseModel):
    """Current diet order and clinically relevant restrictions."""

    order: str | None
    texture: str | None
    liquid_consistency: str | None
    restrictions: list[str]
    preferences: list[str]


class IntakeData(BaseModel):
    """Reported food and fluid intake details."""

    meal_intake: str | None
    fluid_intake: str | None
    appetite: str | None
    assistance: str | None


class LabResult(BaseModel):
    """One laboratory result exactly as represented by the source."""

    name: str
    value: str | None
    unit: str | None
    date: str | None
    reference_range: str | None


class LabsData(BaseModel):
    """Laboratory results grouped under the requested object field."""

    results: list[LabResult]


class MedicationData(BaseModel):
    """One medication listed in the patient documents."""

    name: str
    dose: str | None
    route: str | None
    frequency: str | None
    indication: str | None


class DiagnosisData(BaseModel):
    """One diagnosis listed in the patient documents."""

    name: str
    code: str | None
    date: str | None


class SkinData(BaseModel):
    """Skin integrity and wound information."""

    wounds: list[str]
    pressure_injuries: list[str]
    notes: list[str]


class EdemaData(BaseModel):
    """Presence, location, and severity of edema."""

    present: bool | None
    locations: list[str]
    severity: str | None


class TubeFeedingData(BaseModel):
    """Current enteral feeding order, when present."""

    formula: str | None
    rate: str | None
    schedule: str | None
    flushes: str | None


class SupplementData(BaseModel):
    """One oral or nutrition supplement."""

    name: str
    amount: str | None
    frequency: str | None


class PatientAssessmentData(BaseModel):
    """Strict patient facts extracted from uploaded PDF or text documents."""

    demographics: PatientDemographics
    weight_history: list[WeightHistoryEntry]
    diet: DietData
    intake: IntakeData
    labs: LabsData
    medications: list[MedicationData]
    diagnoses: list[DiagnosisData]
    skin: SkinData
    edema: EdemaData
    tube_feeding: TubeFeedingData | None
    supplements: list[SupplementData]
    notes: list[str]


class RetrievedContext(BaseModel):
    """A retrieved chunk supplied to the assessment model."""

    filename: str
    chunk_text: str
    similarity: float


class AssessmentResponse(BaseModel):
    """Patient extraction, calculations, evidence, and completed ADIME note."""

    patient_data: PatientAssessmentData
    calculations: dict[str, float]
    clinical_context: list[RetrievedContext]
    similar_assessments: list[RetrievedContext]
    adime: str


class AssessmentService:
    """Coordinate extraction, clinical-knowledge retrieval, and ADIME generation."""

    def __init__(
        self,
        open_ai_service: OpenAIService | None = None,
        model: str = ASSESSMENT_MODEL,
    ) -> None:
        """Initialize the assessment service."""
        self.open_ai_service = open_ai_service or OpenAIService()
        self.client = self.open_ai_service.client
        self.model = model
        self.master_prompt = _PROMPT_PATH.read_text(encoding="utf-8")

    def create_assessment(
        self,
        files: list[tuple[str, bytes]],
        query: str | None = None,
    ) -> AssessmentResponse:
        """Run the two OpenAI calls and return their supporting data."""
        patient_data = self.extract_patient_data(files)
        calculations = self.calculate(patient_data)
        retrieval_query = (
            query.strip() if query and query.strip() else self._query_for(patient_data)
        )
        clinical_context, similar_assessments = self.retrieve_context(retrieval_query)
        adime = self.generate_adime(
            patient_data,
            calculations,
            clinical_context,
            similar_assessments,
            query,
        )
        return AssessmentResponse(
            patient_data=patient_data,
            calculations=calculations,
            clinical_context=clinical_context,
            similar_assessments=similar_assessments,
            adime=adime,
        )

    def extract_patient_data(
        self,
        files: list[tuple[str, bytes]],
    ) -> PatientAssessmentData:
        """Extract validated patient facts from one or more PDF files."""
        content: list[dict[str, str]] = [
            {
                "type": "input_text",
                "text": (
                    "Extract patient nutrition-assessment facts from every attached "
                    "document. Use null or an empty collection when data is absent. "
                    "Never infer or invent a clinical fact. Preserve dates and units."
                ),
            },
        ]
        for filename, data in files:
            encoded = base64.b64encode(data).decode("ascii")
            content.append(
                {
                    "type": "input_file",
                    "filename": filename,
                    "file_data": f"data:application/pdf;base64,{encoded}",
                },
            )
        response = self.client.responses.parse(
            model=self.model,
            input=[{"role": "user", "content": content}],
            text_format=PatientAssessmentData,
        )
        if response.output_parsed is None:
            msg = "OpenAI returned no structured patient data"
            raise RuntimeError(msg)
        return response.output_parsed

    @staticmethod
    def calculate(patient: PatientAssessmentData) -> dict[str, float]:
        """Calculate deterministic unit conversions and BMI when inputs exist."""
        output: dict[str, float] = {}
        height = patient.demographics.height_in
        weight = patient.demographics.weight_lb
        if height is not None:
            output["height_cm"] = round(height * 2.54, 1)
        if weight is not None:
            output["weight_kg"] = round(weight / 2.2046226218, 1)
        if height and weight is not None:
            output["bmi"] = round(703 * weight / (height**2), 1)
        return output

    def retrieve_context(
        self,
        query: str,
        top_k: int = 5,
    ) -> tuple[list[RetrievedContext], list[RetrievedContext]]:
        """Retrieve clinical guidance and similar historical assessments."""
        embedding = self.open_ai_service.create_embedding(query)
        vector = "[" + ",".join(str(value) for value in embedding) + "]"
        limit = max(1, min(top_k, 20))
        with self._connect() as connection, connection.cursor() as cursor:
            clinical_context = self._search_document_type(
                cursor,
                vector,
                StoredDocumentType.NUTRITION_CARE_MANUAL,
                limit,
            )
            similar_assessments = self._search_document_type(
                cursor,
                vector,
                StoredDocumentType.ASSESSMENT,
                limit,
            )
        return clinical_context, similar_assessments

    @staticmethod
    def _search_document_type(
        cursor: Cursor[tuple[object, ...]],
        vector: str,
        document_type: StoredDocumentType,
        limit: int,
    ) -> list[RetrievedContext]:
        cursor.execute(
            _SEARCH_SQL,
            (vector, document_type.value, vector, limit),
        )
        rows = cursor.fetchall()
        return [
            RetrievedContext(
                filename=row[0],
                chunk_text=row[1],
                similarity=float(row[2]),
            )
            for row in rows
        ]

    def generate_adime(
        self,
        patient: PatientAssessmentData,
        calculations: dict[str, float],
        clinical_context: list[RetrievedContext],
        similar_assessments: list[RetrievedContext],
        query: str | None,
    ) -> str:
        """Generate an ADIME note from patient facts and retrieved evidence."""
        payload = {
            "patient_data": patient.model_dump(mode="json"),
            "calculations": calculations,
            "retrieved_clinical_context": [
                item.model_dump() for item in clinical_context
            ],
            "similar_past_nutrition_assessments": [
                item.model_dump() for item in similar_assessments
            ],
            "request_focus": query.strip() if query and query.strip() else None,
        }
        response = self.client.responses.create(
            model=self.model,
            instructions=self.master_prompt,
            input=json.dumps(payload, indent=2),
        )
        if not response.output_text.strip():
            msg = "OpenAI returned no completed assessment"
            raise RuntimeError(msg)
        return response.output_text.strip()

    @staticmethod
    def _query_for(patient: PatientAssessmentData) -> str:
        terms = [diagnosis.name for diagnosis in patient.diagnoses]
        terms.extend(patient.skin.wounds)
        terms.extend(patient.skin.pressure_injuries)
        if patient.diet.order:
            terms.append(patient.diet.order)
        return (
            "Clinical nutrition guidance for " + ", ".join(terms)
            if terms
            else DEFAULT_RETRIEVAL_QUERY
        )

    @staticmethod
    def _connect() -> Connection[tuple[object, ...]]:
        connect = import_module("psycopg2").connect
        database_url = str(SETTINGS.database_url).replace(
            "postgresql+psycopg://",
            "postgresql://",
            1,
        )
        return connect(database_url)
