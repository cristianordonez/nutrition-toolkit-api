"""Agent for generating admission nutrition assessments."""

from __future__ import annotations

import json
import pathlib
import typing
from hashlib import sha256

import logfire
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from ntk.models.settings import SETTINGS
from ntk.models.sql.assessment import (
    Assessment,
    AssessmentSource,
)

if typing.TYPE_CHECKING:
    from ntk.models.rag import RagSearchMatch
    from ntk.models.sql.resident import ResidentContext

logfire.configure()
logfire.instrument_pydantic_ai()

ADMISSION_MODEL = "gpt-5.6-terra"
_PROMPT_PATH = pathlib.Path(__file__).parents[1] / "static" / "prompt.md"
_provider = OpenAIProvider(api_key=SETTINGS.open_ai_api_key)
_model = OpenAIResponsesModel(ADMISSION_MODEL, provider=_provider)
admission_agent = Agent(
    _model,
    output_type=str,
    instructions=_PROMPT_PATH.read_text(encoding="utf-8"),
)


class AdmissionAgent:
    """Create a nutrition assessment from resident and retrieved context."""

    def __init__(
        self,
        agent: Agent[None, str] | None = None,
    ) -> None:
        """Initialize the assessment agent or use an injected test double."""
        self.agent = agent or admission_agent

    async def generate(
        self,
        resident_data: ResidentContext,
        retrieved_knowledge: list[RagSearchMatch],
        previous_assessments: list[RagSearchMatch],
        request_focus: str | None = None,
    ) -> Assessment:
        """Generate a note from the three explicitly defined input sources."""
        payload = {
            "resident_data": resident_data.clinical_payload(),
            "retrieved_knowledge": [
                match.model_dump(mode="json") for match in retrieved_knowledge
            ],
            "previous_assessments": [
                match.model_dump(mode="json") for match in previous_assessments
            ],
            "request_focus": request_focus,
        }
        result = await self.agent.run(json.dumps(payload, default=str))
        note = result.output.strip()
        if not note:
            msg = "Assessment agent returned an empty note"
            raise RuntimeError(msg)
        return Assessment(
            content=note,
            source=AssessmentSource.GENERATED,
            source_filename=None,
            content_hash=sha256(" ".join(note.split()).encode()).hexdigest(),
            assessment_index=0,
            created_by=ADMISSION_MODEL,
        )
