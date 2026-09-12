from __future__ import annotations

import typing

from ntk.models.knowledge import KnowledgeType
from ntk.repositories.embedding_repo import EmbeddingRepo


class _Result:
    @staticmethod
    def all() -> list[tuple[object, ...]]:
        return []


class _Session:
    sql = ""
    params: typing.ClassVar[dict[str, object]] = {}

    @classmethod
    def exec(
        cls,
        statement: object,
        *,
        params: dict[str, object],
    ) -> _Result:
        cls.sql = str(statement)
        cls.params = params
        return _Result()


def test_assessment_search_only_uses_finalized_assessments() -> None:
    session = _Session()

    matches = EmbeddingRepo(
        typing.cast("typing.Any", session),
    ).search_assessments("[0.1]", 5)

    assert matches == []
    assert "WHERE a.status = :finalized_status" in session.sql
    assert session.params["finalized_status"] == "finalized"


def test_diet_manual_search_limits_knowledge_type() -> None:
    session = _Session()

    matches = EmbeddingRepo(
        typing.cast("typing.Any", session),
    ).search_knowledge(
        "[0.1]",
        3,
        document_type=KnowledgeType.DIET_MANUAL,
    )

    assert matches == []
    assert session.params["include_diet_manual"] is True
    assert session.params["include_nutrition_care_manual"] is False
    assert session.params["diet_manual"] == "diet-manual"


def test_nutrition_care_manual_search_limits_knowledge_type() -> None:
    session = _Session()

    matches = EmbeddingRepo(
        typing.cast("typing.Any", session),
    ).search_knowledge(
        "[0.1]",
        3,
        document_type=KnowledgeType.NUTRITION_CARE_MANUAL,
    )

    assert matches == []
    assert session.params["include_diet_manual"] is False
    assert session.params["include_nutrition_care_manual"] is True
    assert session.params["nutrition_care_manual"] == "nutrition-care-manual"


def test_knowledge_search_includes_both_manuals_by_default() -> None:
    session = _Session()

    matches = EmbeddingRepo(
        typing.cast("typing.Any", session),
    ).search_knowledge("[0.1]", 3)

    assert matches == []
    assert session.params["include_diet_manual"] is True
    assert session.params["include_nutrition_care_manual"] is True
    assert ":include_diet_manual" in session.sql
    assert ":include_nutrition_care_manual" in session.sql


def test_knowledge_search_returns_chunk_provenance() -> None:
    class Result:
        @staticmethod
        def all() -> list[tuple[object, ...]]:
            return [
                (
                    9,
                    "diet-manual.pdf",
                    "Full Liquid Diet\nClinical guidance",
                    0.84,
                    "diet-manual",
                    "Full Liquid Diet",
                    113,
                    114,
                ),
            ]

    class Session:
        sql = ""

        @classmethod
        def exec(
            cls,
            statement: object,
            *,
            params: dict[str, object],
        ) -> Result:
            del params
            cls.sql = str(statement)
            return Result()

    session = Session()

    matches = EmbeddingRepo(
        typing.cast("typing.Any", session),
    ).search_knowledge("[0.1]", 1)

    assert matches[0].knowledge_type is KnowledgeType.DIET_MANUAL
    assert matches[0].section_title == "Full Liquid Diet"
    assert matches[0].source_page_start == 113  # noqa: PLR2004
    assert matches[0].source_page_end == 114  # noqa: PLR2004
    assert "c.source_page_start" in session.sql
