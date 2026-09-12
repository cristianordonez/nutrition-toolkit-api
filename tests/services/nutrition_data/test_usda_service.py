from __future__ import annotations

import typing
from http import HTTPStatus

import pytest
import requests

from ntk.services.nutrition_data.usda import FOODS_URL, LIST_URL, USDAService

if typing.TYPE_CHECKING:
    from ntk.services.nutrition_data.usda_transformer import USDAFoodRecord


class Response:
    def __init__(
        self,
        payload: object,
        status_code: int = HTTPStatus.OK,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self) -> object:
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= HTTPStatus.BAD_REQUEST:
            raise requests.HTTPError(str(self.status_code))


class HTTPClient:
    def __init__(self, responses: list[Response]) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, object],
        timeout: int,
    ) -> Response:
        assert timeout == 30  # noqa: PLR2004
        self.calls.append((url, params))
        return next(self.responses)


class Repository:
    def __init__(self, last_completed_page: int = 0) -> None:
        self.last_completed_page = last_completed_page
        self.persisted: list[tuple[str, int, list[USDAFoodRecord]]] = []

    def get_last_completed_page(self, _source: str) -> int:
        return self.last_completed_page

    def persist_page(
        self,
        source: str,
        page_number: int,
        records: typing.Iterable[USDAFoodRecord],
    ) -> int:
        record_list = list(records)
        self.persisted.append((source, page_number, record_list))
        self.last_completed_page = page_number
        return len(record_list)


def food(fdc_id: int) -> dict[str, object]:
    return {
        "fdcId": fdc_id,
        "description": f"Food {fdc_id}",
        "dataType": "Foundation",
        "publicationDate": "2026-04-30",
        "foodCategory": {"description": "Fish"},
        "foodNutrients": [],
    }


def test_sync_resumes_after_checkpoint_and_fetches_full_foods() -> None:
    repository = Repository(last_completed_page=99)
    http_client = HTTPClient(
        [
            Response([{"fdcId": 10}, {"fdcId": 11}]),
            Response([food(10), food(11)]),
        ],
    )
    service = USDAService(
        typing.cast("typing.Any", repository),
        api_key="test-key",
        http_client=http_client,
    )

    result = service.sync_foods(page_size=50, max_pages=1)

    assert result.foods_synced == 2  # noqa: PLR2004
    assert result.last_completed_page == 100  # noqa: PLR2004
    assert http_client.calls[0] == (
        LIST_URL,
        {
            "dataType": ["Foundation", "Branded", "Survey (FNDDS)"],
            "pageSize": 50,
            "pageNumber": 100,
            "api_key": "test-key",
        },
    )
    assert http_client.calls[1][0] == FOODS_URL
    assert http_client.calls[1][1]["fdcIds"] == "10,11"
    assert repository.persisted[0][1] == 100  # noqa: PLR2004


def test_get_foods_batches_ids_at_usda_limit() -> None:
    identifiers = list(range(1, 22))
    http_client = HTTPClient(
        [Response([food(value) for value in range(1, 21)]), Response([food(21)])],
    )
    service = USDAService(
        typing.cast("typing.Any", Repository()),
        api_key="test-key",
        http_client=http_client,
    )

    assert len(service.get_foods(identifiers)) == len(identifiers)
    assert [call[1]["fdcIds"] for call in http_client.calls] == [
        ",".join(str(value) for value in range(1, 21)),
        "21",
    ]


def test_rate_limit_uses_exponential_backoff() -> None:
    delays: list[float] = []
    http_client = HTTPClient(
        [
            Response([], HTTPStatus.TOO_MANY_REQUESTS),
            Response([], HTTPStatus.TOO_MANY_REQUESTS),
            Response([]),
        ],
    )
    service = USDAService(
        typing.cast("typing.Any", Repository()),
        api_key="test-key",
        http_client=http_client,
        sleep=delays.append,
    )

    assert service.list_foods() == []
    assert delays == [1.0, 2.0]


def test_incomplete_detail_response_does_not_advance_checkpoint() -> None:
    repository = Repository()
    http_client = HTTPClient(
        [Response([{"fdcId": 10}, {"fdcId": 11}]), Response([food(10)])],
    )
    service = USDAService(
        typing.cast("typing.Any", repository),
        api_key="test-key",
        http_client=http_client,
    )

    with pytest.raises(ValueError, match=r"missing=\[11\]"):
        service.sync_foods(page_size=2)

    assert repository.persisted == []
    assert repository.last_completed_page == 0
