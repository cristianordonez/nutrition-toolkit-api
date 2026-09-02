from __future__ import annotations

import typing

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
