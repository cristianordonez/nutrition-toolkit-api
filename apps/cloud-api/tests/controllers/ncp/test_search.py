from __future__ import annotations

import asyncio

import pytest

from api.controllers.ncp import search
from api.controllers.ncp.search import (
    NCPSearchController,
    NCPSearchOptions,
    NCPSearchResponse,
)
from api.models.rag import RagSearchMatch


def test_ncp_search_embeds_and_filters_ncps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = 42
    match = RagSearchMatch(
        document_id=document_id,
        filename="assessment.pdf",
        chunk_text="ADIME",
        similarity=0.91,
    )

    class Service:
        def __init__(self, repository: object) -> None:
            self.repository = repository

        def search_ncps(
            self,
            text: str,
            person_identifier: str,
            top_k: int,
        ) -> list[RagSearchMatch]:
            assert text == "  weight loss  "
            assert person_identifier == "person-1"
            assert top_k == 3  # noqa: PLR2004
            return [match]

    monkeypatch.setattr(search, "EmbeddingService", Service)
    controller = NCPSearchController(session=object())  # ty: ignore[invalid-argument-type]

    output = controller.run(
        NCPSearchOptions(
            text="  weight loss  ",
            person_identifier="person-1",
            top_k=3,
        ),
    )

    assert output.result.matches[0].document_id == document_id
    assert output.result.to_console() == "# assessment.pdf (0.9100)\nADIME"


def test_ncp_search_labels_generated_ncp_without_filename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = RagSearchMatch(
        document_id=43,
        filename="generated-ncp",
        chunk_text="Generated ADIME",
        similarity=0.8,
    )

    class Service:
        def __init__(self, repository: object) -> None:
            self.repository = repository

        def search_ncps(
            self,
            text: str,
            person_identifier: str,
            top_k: int,
        ) -> list[RagSearchMatch]:
            assert text == "generated"
            assert person_identifier == "person-1"
            assert top_k == 5  # noqa: PLR2004
            return [match]

    monkeypatch.setattr(search, "EmbeddingService", Service)
    controller = NCPSearchController(session=object())  # ty: ignore[invalid-argument-type]

    output = controller.run(
        NCPSearchOptions(text="generated", person_identifier="person-1"),
    )

    assert output.result.matches[0].filename == "generated-ncp"


def test_ncp_search_async_entry_point_uses_async_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = RagSearchMatch(
        document_id=44,
        filename="assessment.pdf",
        chunk_text="ADIME",
        similarity=0.75,
    )

    class Service:
        def __init__(self, repository: object) -> None:
            self.repository = repository

        @staticmethod
        async def search_ncps_async(
            text: str,
            person_identifier: str,
            top_k: int,
        ) -> list[RagSearchMatch]:
            assert text == "weight loss"
            assert person_identifier == "person-1"
            assert top_k == 2  # noqa: PLR2004
            return [match]

    monkeypatch.setattr(search, "EmbeddingService", Service)
    controller = NCPSearchController(session=object())  # ty: ignore[invalid-argument-type]

    output = asyncio.run(controller.search("weight loss", "person-1", top_k=2))

    assert output.result.matches == [match]


def test_ncp_search_rejects_blank_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Service:
        def __init__(self, repository: object) -> None:
            self.repository = repository

        def search_ncps(
            self,
            text: str,
            person_identifier: str,
            top_k: int,
        ) -> list[RagSearchMatch]:
            assert text == " "
            assert person_identifier == "person-1"
            assert top_k == 5  # noqa: PLR2004
            message = "Search text must not be empty"
            raise ValueError(message)

    monkeypatch.setattr(search, "EmbeddingService", Service)
    controller = NCPSearchController(session=object())  # ty: ignore[invalid-argument-type]

    with pytest.raises(ValueError, match="must not be empty"):
        controller.run(NCPSearchOptions(text=" ", person_identifier="person-1"))


def test_ncp_search_response_renders_no_matches() -> None:
    assert NCPSearchResponse(matches=[]).to_console() == ""
