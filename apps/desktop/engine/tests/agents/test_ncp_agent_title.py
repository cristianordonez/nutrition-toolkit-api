from __future__ import annotations

import asyncio
import typing
from types import SimpleNamespace

import pytest

from engine.agents.ncp_agent import NOTE_TITLES, NCPAgent, with_title
from engine.models.ncp_context import NCPGenerationRequest
from engine.models.ncp_note import NCPNoteType


class _Model:
    """Stands in for the note agent; heads its note with the wrong title."""

    async def run(self, _prompt: str, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            output="Nutrition Follow Up\nResident seen by wound care.",
        )


def test_the_generated_note_carries_the_requested_title() -> None:
    request = NCPGenerationRequest.model_construct(
        person_identifier="EX1",
        note_type=NCPNoteType.WOUND,
        summary_text="",
        person=typing.cast("typing.Any", {}),
    )

    note = asyncio.run(NCPAgent(agent=_Model()).run(request))

    assert note.splitlines() == [
        "Nutrition Wound Note",
        "Resident seen by wound care.",
    ]


def test_the_unbudgeted_summary_is_never_sent_to_the_model() -> None:
    prompts: list[str] = []

    class _Recorder(_Model):
        async def run(self, _prompt: str, **_kwargs: object) -> SimpleNamespace:
            prompts.append(_prompt)
            return await super().run(_prompt, **_kwargs)

    request = NCPGenerationRequest.model_construct(
        person_identifier="EX1",
        note_type=NCPNoteType.FOLLOW_UP,
        summary_text="UNBUDGETED-SUMMARY",
        person=typing.cast("typing.Any", {}),
    )

    asyncio.run(NCPAgent(agent=_Recorder()).run(request))

    assert "summary_text" not in prompts[0]
    assert "UNBUDGETED-SUMMARY" not in prompts[0]


@pytest.mark.parametrize(
    ("note", "note_type", "expected_first_line"),
    [
        (
            "Nutrition Follow Up\nResident seen.",
            NCPNoteType.WOUND,
            "Nutrition Wound Note",
        ),
        (
            "**Nutrition Quarterly Assessment**\nResident seen.",
            NCPNoteType.FOLLOW_UP,
            "Nutrition Follow Up",
        ),
        (
            "Resident seen by wound care on 9/1.",
            NCPNoteType.WOUND,
            "Nutrition Wound Note",
        ),
        (
            "Nutrition Wound Note\nResident seen.",
            NCPNoteType.WOUND,
            "Nutrition Wound Note",
        ),
    ],
)
def test_the_selected_type_sets_the_title(
    note: str,
    note_type: NCPNoteType,
    expected_first_line: str,
) -> None:
    titled = with_title(note, note_type)

    lines = titled.splitlines()
    assert lines[0] == expected_first_line
    assert lines[1].startswith("Resident seen")
    assert sum(line.startswith(("Nutrition", "**Nutrition")) for line in lines) == 1


def test_a_first_sentence_is_never_mistaken_for_a_title() -> None:
    note = "Nutrition intake remains poor at 25% of meals.\nMonitoring: weekly."

    assert with_title(note, NCPNoteType.FOLLOW_UP).splitlines() == [
        "Nutrition Follow Up",
        "Nutrition intake remains poor at 25% of meals.",
        "Monitoring: weekly.",
    ]


def test_every_note_type_has_a_title() -> None:
    assert set(NOTE_TITLES) == set(NCPNoteType)
