"""Turn a provider's transport failures into errors that carry no content.

Wraps any pydantic-ai model. A timeout, a refused connection or an HTTP error
becomes the provider's own ``AIProviderError`` subclass with a sentence a
dietitian can read; the underlying exception type goes in ``diagnostic``.
Nothing here logs a request or response -- only how long a request took.
"""

from __future__ import annotations

import logging
import time
import typing

import httpx
import httpx2
import openai
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.models.wrapper import WrapperModel

if typing.TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage, ModelResponse
    from pydantic_ai.models import Model, ModelRequestParameters
    from pydantic_ai.settings import ModelSettings

    from engine.services.ai.errors import AIProviderUnavailableError, AITimeoutError

logger = logging.getLogger(__name__)

_HTTP_BAD_REQUEST = 400
_HTTP_UNAUTHORIZED = 401
_HTTP_SERVER_ERROR = 500


class ProviderErrorBoundary(WrapperModel):
    """Forward requests to ``wrapped``, translating failures for ``label``."""

    def __init__(
        self,
        wrapped: Model,
        *,
        label: str,
        recorded_name: str,
        unavailable: type[AIProviderUnavailableError],
        timeout: type[AITimeoutError],
    ) -> None:
        """Name the provider and the error types its failures become.

        ``recorded_name`` is what extracted facts store as the model that
        produced them, e.g. ``local`` or ``openai:gpt-5.6-luna``.
        """
        super().__init__(wrapped)
        self.provider_label = label
        self.recorded_name = recorded_name
        self._unavailable = unavailable
        self._timeout = timeout

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        """Forward one request, translating failures."""
        started = time.monotonic()
        try:
            response = await super().request(
                messages,
                model_settings,
                model_request_parameters,
            )
        except ModelHTTPError as error:
            raise self._http_failure(error.status_code) from error
        except (
            ModelAPIError,
            openai.APIError,
            httpx.HTTPError,
            httpx2.HTTPError,
        ) as error:
            if _is_timeout(error):
                msg = f"{self.provider_label} did not answer in time."
                raise self._timeout(msg) from error
            msg = f"{self.provider_label} is not available."
            raise self._unavailable(msg, diagnostic=type(error).__name__) from error
        logger.info(
            "%s request completed in %.1f seconds",
            self.provider_label,
            time.monotonic() - started,
        )
        return response

    def _http_failure(self, status_code: int) -> AIProviderUnavailableError:
        diagnostic = f"{self.provider_label} answered HTTP {status_code}"
        if status_code == _HTTP_BAD_REQUEST:
            msg = (
                f"{self.provider_label} could not process this request. It may be "
                "longer than the model accepts."
            )
        elif status_code == _HTTP_UNAUTHORIZED:
            msg = f"{self.provider_label} rejected the API key."
        elif status_code >= _HTTP_SERVER_ERROR:
            msg = f"{self.provider_label} failed while generating a response."
        else:
            msg = f"{self.provider_label} refused the request."
        return self._unavailable(msg, diagnostic=diagnostic)


def recorded_name_of(model: object) -> str | None:
    """Return the name to record for facts a model produced."""
    recorded = getattr(model, "recorded_name", None)
    if recorded is not None:
        return str(recorded)
    name = getattr(model, "model_name", None)
    return str(name) if name is not None else None


def _is_timeout(error: BaseException) -> bool:
    """Report whether a timeout caused ``error`` (pydantic-ai wraps it)."""
    current: BaseException | None = error
    while current is not None:
        if isinstance(
            current,
            (openai.APITimeoutError, httpx.TimeoutException, httpx2.TimeoutException),
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


__all__ = ["ProviderErrorBoundary", "recorded_name_of"]
