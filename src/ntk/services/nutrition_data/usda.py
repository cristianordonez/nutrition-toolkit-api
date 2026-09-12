"""USDA FoodData Central pagination and synchronization service."""

from __future__ import annotations

import time
import typing
from http import HTTPStatus

import requests
from pydantic import BaseModel

from ntk.models.settings import SETTINGS
from ntk.services.nutrition_data.usda_transformer import USDAResponseTransformer

if typing.TYPE_CHECKING:
    from ntk.repositories.food_repo import FoodRepo


class _Response(typing.Protocol):
    status_code: int

    @property
    def headers(self) -> typing.Mapping[str, str]: ...

    def json(self) -> object: ...

    def raise_for_status(self) -> None: ...


class _HTTPClient(typing.Protocol):
    def get(
        self,
        url: str,
        *,
        params: dict[str, object],
        timeout: int,
    ) -> _Response: ...


BASE_URL = "https://api.nal.usda.gov/fdc/v1"
LIST_URL = f"{BASE_URL}/foods/list"
FOODS_URL = f"{BASE_URL}/foods"
DEFAULT_DATA_TYPES = ("Foundation", "Branded", "Survey (FNDDS)")
MAX_LIST_PAGE_SIZE = 200
DETAIL_BATCH_SIZE = 20


class USDASyncResult(BaseModel):
    """Summary of one resumable USDA synchronization run."""

    foods_synced: int
    pages_completed: int
    last_completed_page: int
    exhausted: bool


class USDAService:
    """Fetch USDA foods and persist complete pages with resumable checkpoints."""

    source = "usda-food-data-central"

    def __init__(  # noqa: PLR0913
        self,
        repository: FoodRepo,
        *,
        api_key: str | None = None,
        http_client: _HTTPClient | None = None,
        sleep: typing.Callable[[float], None] = time.sleep,
        max_retries: int = 5,
        backoff_base_seconds: float = 1.0,
        max_backoff_seconds: float = 60.0,
    ) -> None:
        """Configure persistence, HTTP access, and rate-limit retry behavior."""
        if max_retries < 0:
            msg = "max_retries cannot be negative"
            raise ValueError(msg)
        self.repository = repository
        self.api_key = api_key or SETTINGS.usda_api_key
        self.http_client = http_client or typing.cast("_HTTPClient", requests)
        self.sleep = sleep
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.max_backoff_seconds = max_backoff_seconds

    def sync_foods(
        self,
        *,
        page_size: int = 50,
        start_page: int = 1,
        max_pages: int | None = None,
    ) -> USDASyncResult:
        """Resume at the next uncommitted list page and persist full food data."""
        self._validate_paging(page_size, start_page, max_pages)
        last_completed_page = self.repository.get_last_completed_page(self.source)
        page_number = max(start_page, last_completed_page + 1)
        foods_synced = 0
        pages_completed = 0
        exhausted = False

        while max_pages is None or pages_completed < max_pages:
            listed_foods = self.list_foods(
                page_size=page_size,
                page_number=page_number,
            )
            if not listed_foods:
                exhausted = True
                break
            fdc_ids = self._fdc_ids(listed_foods)
            full_foods = self.get_foods(fdc_ids)
            self._validate_details(fdc_ids, full_foods)
            records = USDAResponseTransformer.transform_many(full_foods)
            foods_synced += self.repository.persist_page(
                self.source,
                page_number,
                records,
            )
            pages_completed += 1
            last_completed_page = page_number
            if len(listed_foods) < page_size:
                exhausted = True
                break
            page_number += 1

        return USDASyncResult(
            foods_synced=foods_synced,
            pages_completed=pages_completed,
            last_completed_page=last_completed_page,
            exhausted=exhausted,
        )

    def list_foods(
        self,
        *,
        page_size: int = 50,
        page_number: int = 1,
    ) -> list[dict[str, typing.Any]]:
        """Return one abridged page from the USDA food-list endpoint."""
        response = self._get(
            LIST_URL,
            params={
                "dataType": list(DEFAULT_DATA_TYPES),
                "pageSize": page_size,
                "pageNumber": page_number,
                "api_key": self.api_key,
            },
        )
        return self._food_list(response.json())

    def get_foods(self, fdc_ids: typing.Iterable[int]) -> list[dict[str, typing.Any]]:
        """Fetch full foods in USDA-supported batches of FDC IDs."""
        identifiers = list(dict.fromkeys(fdc_ids))
        foods: list[dict[str, typing.Any]] = []
        for offset in range(0, len(identifiers), DETAIL_BATCH_SIZE):
            batch = identifiers[offset : offset + DETAIL_BATCH_SIZE]
            response = self._get(
                FOODS_URL,
                params={
                    "fdcIds": ",".join(str(fdc_id) for fdc_id in batch),
                    "format": "full",
                    "api_key": self.api_key,
                },
            )
            foods.extend(self._food_list(response.json()))
        return foods

    def _get(
        self,
        url: str,
        *,
        params: dict[str, object],
    ) -> _Response:
        for retry_number in range(self.max_retries + 1):
            response = self.http_client.get(url, params=params, timeout=30)
            if response.status_code != HTTPStatus.TOO_MANY_REQUESTS:
                response.raise_for_status()
                return response
            if retry_number == self.max_retries:
                response.raise_for_status()
            self.sleep(self._backoff_delay(retry_number, response.headers))
        msg = "USDA request retry loop exited unexpectedly"
        raise RuntimeError(msg)

    def _backoff_delay(
        self,
        retry_number: int,
        headers: typing.Mapping[str, str],
    ) -> float:
        exponential_delay = min(
            self.backoff_base_seconds * (2**retry_number),
            self.max_backoff_seconds,
        )
        retry_after = headers.get("Retry-After")
        if retry_after is None:
            return exponential_delay
        try:
            return max(exponential_delay, float(retry_after))
        except ValueError:
            return exponential_delay

    @staticmethod
    def _food_list(payload: object) -> list[dict[str, typing.Any]]:
        if not isinstance(payload, list) or not all(
            isinstance(item, dict) for item in payload
        ):
            msg = "USDA food endpoint returned an unexpected response"
            raise ValueError(msg)
        return typing.cast("list[dict[str, typing.Any]]", payload)

    @staticmethod
    def _fdc_ids(foods: typing.Iterable[dict[str, typing.Any]]) -> list[int]:
        try:
            return list(dict.fromkeys(int(food["fdcId"]) for food in foods))
        except (KeyError, TypeError, ValueError) as error:
            msg = "USDA list response contains an invalid FDC ID"
            raise ValueError(msg) from error

    @staticmethod
    def _validate_details(
        requested_ids: typing.Iterable[int],
        foods: typing.Iterable[dict[str, typing.Any]],
    ) -> None:
        requested = set(requested_ids)
        try:
            received = {int(food["fdcId"]) for food in foods}
        except (KeyError, TypeError, ValueError) as error:
            msg = "USDA detail response contains an invalid FDC ID"
            raise ValueError(msg) from error
        if requested != received:
            missing = sorted(requested - received)
            unexpected = sorted(received - requested)
            msg = (
                "USDA detail response did not match the requested FDC IDs: "
                f"missing={missing}, unexpected={unexpected}"
            )
            raise ValueError(msg)

    @staticmethod
    def _validate_paging(
        page_size: int,
        start_page: int,
        max_pages: int | None,
    ) -> None:
        if not 1 <= page_size <= MAX_LIST_PAGE_SIZE:
            msg = f"page_size must be between 1 and {MAX_LIST_PAGE_SIZE}"
            raise ValueError(msg)
        if start_page < 1:
            msg = "start_page must be at least 1"
            raise ValueError(msg)
        if max_pages is not None and max_pages < 1:
            msg = "max_pages must be at least 1"
            raise ValueError(msg)


__all__ = ["USDAService", "USDASyncResult"]
