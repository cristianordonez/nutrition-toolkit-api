"""On-device Nutrition Care Process note generation.

Runs where the clinical data already lives, so generating a note sends no
resident information anywhere by default. The model comes from
``engine.services.ai.controller.AIController``: Local AI unless the user chose
OpenAI in Settings. This module never knows which one answered.

The agent can search the diet and nutrition-care manuals in the local
knowledge base (``engine.agents.tools``). The note's format is the prompt's
job; the one thing set in code is the title, which follows the note type the
reviewer chose (``with_title``).
"""

from __future__ import annotations

import asyncio
import re
import typing

import logfire
from pydantic_ai import Agent

from engine.agents.prompts import ncp_instructions
from engine.agents.tools import (
    CALCULATOR_TOOLSET,
    KNOWLEDGE_SEARCH_TOOLSET,
    KnowledgeSearchToolDependencies,
)
from engine.models.ncp_note import NCPNoteType
from engine.services.ai.controller import AIController, ai_controller

if typing.TYPE_CHECKING:
    from collections.abc import Mapping

    from engine.models.ncp_context import NCPGenerationRequest
    from engine.services.embedding_service import EmbeddingService

# Traces keep timings and model names only. Prompts and completions hold
# clinical data and must never be exported, whichever provider runs them.
logfire.instrument_pydantic_ai(include_content=False, include_binary_content=False)

#: A local model is far slower than a hosted one, and a note that takes several
#: minutes is still useful -- but an unbounded wait is not, because the desktop
#: shell blocks on this call.
_GENERATION_TIMEOUT_SECONDS = 600

#: The heading each requested note type is written under. The reviewer's
#: choice sets it; the model does not re-derive it from the record.
NOTE_TITLES: Mapping[NCPNoteType, str] = {
    NCPNoteType.ADMISSION: "Nutrition Admission Assessment",
    NCPNoteType.READMISSION: "Nutrition Readmission Note",
    NCPNoteType.SIGNIFICANT_CHANGE: "Nutrition Significant Change Note",
    NCPNoteType.WOUND: "Nutrition Wound Note",
    NCPNoteType.ANNUAL: "Nutrition Annual Assessment",
    NCPNoteType.QUARTERLY: "Nutrition Quarterly Assessment",
    NCPNoteType.FOLLOW_UP: "Nutrition Follow Up",
    NCPNoteType.PAYER_CHANGE: "Nutrition Payer Change Assessment",
    NCPNoteType.HIGH_RISK: "Nutrition High Risk Note",
}

#: A first line that is a title rather than the note's first sentence.
_TITLE_LINE = re.compile(r"^[#*_\s]*nutrition\b[^.:]{0,60}?[*_\s]*$", re.IGNORECASE)


def with_title(note: str, note_type: NCPNoteType) -> str:
    """Return ``note`` headed by its type's title, whatever the model wrote.

    A title-like first line is replaced, so a note requested as a wound note
    can never come back headed "Nutrition Follow Up"; a note without one gets
    the title added above it.
    """
    title = NOTE_TITLES[note_type]
    lines = note.strip().splitlines()
    if lines and _TITLE_LINE.match(lines[0]):
        lines = lines[1:]
    body = "\n".join(lines).strip()
    return f"{title}\n{body}" if body else title


class NCPGenerationTimeoutError(TimeoutError):
    """Raised when the model exceeds the generation deadline."""


def build_ncp_agent(
    ai: AIController | None = None,
) -> Agent[KnowledgeSearchToolDependencies, str]:
    """Build the note-generation agent.

    Built on demand rather than at import so the engine still imports with no
    model reachable at all.

    The calculator tools take no dependencies, so the agent's dependency type
    is the one the manual lookups need; the calculators simply ignore it.
    """
    return Agent(
        (ai or ai_controller()).model(),
        output_type=str,
        deps_type=KnowledgeSearchToolDependencies,
        instructions=ncp_instructions(),
        toolsets=[CALCULATOR_TOOLSET, KNOWLEDGE_SEARCH_TOOLSET],
    )


class NCPAgent:
    """Generate a Nutrition Care Process note on this device."""

    def __init__(
        self,
        agent: object | None = None,
        knowledge_service: EmbeddingService | None = None,
        *,
        ai: AIController | None = None,
    ) -> None:
        """Store an injected agent, building the real one only when used.

        ``knowledge_service`` is what the manual-lookup tools run against. It
        is optional: a note can still be written without it, from the prompt's
        own clinical rules and the resident's supplied facts. A lookup
        attempted without one fails that tool call rather than the run.
        """
        self._agent = agent
        self._knowledge_service = knowledge_service
        self._ai = ai

    async def run(self, request: NCPGenerationRequest) -> str:
        """Generate one note from a prepared generation request."""
        agent = self._agent or build_ncp_agent(self._ai)
        try:
            async with asyncio.timeout(_GENERATION_TIMEOUT_SECONDS):
                result = await agent.run(  # ty: ignore[unresolved-attribute]
                    request.model_dump_json(exclude_none=True),
                    deps=KnowledgeSearchToolDependencies(
                        knowledge_service=self._knowledge_service,
                    ),
                )
        except TimeoutError as error:
            message = (
                f"Note generation timed out after {_GENERATION_TIMEOUT_SECONDS} seconds"
            )
            raise NCPGenerationTimeoutError(message) from error
        note = str(result.output).strip()
        if not note:
            message = "The model returned an empty note"
            raise RuntimeError(message)
        return with_title(note, request.note_type)


__all__ = [
    "NOTE_TITLES",
    "NCPAgent",
    "NCPGenerationTimeoutError",
    "build_ncp_agent",
    "with_title",
]
