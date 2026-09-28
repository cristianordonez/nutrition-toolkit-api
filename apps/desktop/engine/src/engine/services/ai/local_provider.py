"""Local AI: a llama.cpp server on this machine, reached over localhost.

The provider only knows a URL (``NUTRITION_AI_LLAMA_URL``). It does not care
how llama-server was started -- by hand, by a test, or later by the desktop
app -- nor where its executable or model file live.

Two things specific to llama.cpp live only here:

* Structured output is native: an agent's Pydantic output type becomes a JSON
  schema sent as ``response_format``, which llama-server compiles to a grammar
  so the model can only emit conforming JSON, which pydantic-ai validates.
* The URL must be this machine, so clinical text cannot be sent to another
  host by configuration mistake.
"""

from __future__ import annotations

import ipaddress
import logging
import pathlib
import typing
import urllib.parse

import httpx2
import openai
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIJsonSchemaTransformer
from pydantic_ai.providers.openai import OpenAIProvider as OpenAICompatibleProvider
from pydantic_ai.settings import ModelSettings

from engine.models.ai import AIProvider, AIStatus, AIStatusValue
from engine.services.ai.boundary import ProviderErrorBoundary
from engine.services.ai.errors import (
    LocalAITimeoutError,
    LocalAIUnavailableError,
    ProviderConfigurationError,
)

if typing.TYPE_CHECKING:
    from pydantic_ai._json_schema import JsonSchema
    from pydantic_ai.models import Model

    from engine.models.settings import LocalAISettings

logger = logging.getLogger(__name__)

#: The model name sent with each request. llama-server serves whichever model
#: it loaded and ignores the name, so nothing here depends on a file name.
MODEL_NAME = "local"

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
#: An API key is required by the OpenAI client; a server started without
#: ``--api-key`` ignores it.
_NO_API_KEY = "no-key"
_HEALTH_TIMEOUT_SECONDS = 2.0
_HTTP_OK = 200
_HTTP_SERVICE_UNAVAILABLE = 503


class LocalJsonSchemaTransformer(OpenAIJsonSchemaTransformer):
    """Make single-valued properties required, so the grammar emits them.

    llama.cpp's grammar only forces properties the schema lists as required.
    A discriminated union's tag (``type: Literal["weight"] = "weight"``) has a
    default, so Pydantic leaves it optional -- the model may then omit it,
    and validation cannot tell which union member it wrote. A property with
    exactly one allowed value costs the model nothing to emit, so requiring
    it changes no meaning and makes every union member identifiable.
    """

    def transform(self, schema: JsonSchema) -> JsonSchema:
        """Apply OpenAI's transform, then require single-valued properties."""
        schema = super().transform(schema)
        properties = schema.get("properties")
        if isinstance(properties, dict):
            required = list(schema.get("required", []))
            for name, definition in properties.items():
                if name not in required and _is_single_valued(definition):
                    required.append(name)
            if required:
                schema["required"] = required
        return schema


def _is_single_valued(definition: object) -> bool:
    if not isinstance(definition, dict):
        return False
    if "const" in definition:
        return True
    enum = definition.get("enum")
    return isinstance(enum, list) and len(enum) == 1


#: llama-server compiles ``response_format`` JSON schemas to a grammar, so
#: native structured output is the reliable mode; tool-call output is not.
LOCAL_MODEL_PROFILE: dict[str, typing.Any] = {
    "default_structured_output_mode": "native",
    "json_schema_transformer": LocalJsonSchemaTransformer,
    "supports_json_schema_output": True,
    "supports_json_object_output": True,
    "supported_native_tools": frozenset(),
}


def validate_local_url(url: str) -> str:
    """Return the llama-server URL, refusing any other machine."""
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        msg = (
            "NUTRITION_AI_LLAMA_URL must be an http(s) URL, e.g. http://127.0.0.1:8080."
        )
        raise ProviderConfigurationError(msg)
    if not _is_local_host(parsed.hostname):
        msg = (
            "NUTRITION_AI_LLAMA_URL must point to this machine "
            "(127.0.0.1 or localhost). Clinical data is not sent to "
            "other machines."
        )
        raise ProviderConfigurationError(msg)
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""),
    )


def display_model_name(loaded: str) -> str:
    """Return the name to show for a loaded model, never its full path.

    llama-server names a model by the file it loaded (a path naming the
    user's folders) unless it was started with ``--alias``.
    """
    # PureWindowsPath splits on both "/" and "\\", so either OS's path works.
    name = pathlib.PureWindowsPath(loaded).name
    return name[: -len(".gguf")] if name.casefold().endswith(".gguf") else name


def _is_local_host(host: str) -> bool:
    if host.casefold() in _LOCAL_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class LocalAIProvider:
    """Models that run on the configured local llama.cpp server."""

    kind = AIProvider.LOCAL

    def __init__(
        self,
        settings: LocalAISettings,
        *,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        """Bind to the configured URL; nothing is contacted until used."""
        self.settings = settings
        self._http_client = http_client

    @property
    def base_url(self) -> str:
        """Return the validated server URL."""
        return validate_local_url(self.settings.llama_url)

    def model(self) -> Model:
        """Return a model on the local server (it serves the one it loaded)."""
        client = openai.AsyncOpenAI(
            base_url=f"{self.base_url}/v1",
            api_key=self.settings.llama_api_key or _NO_API_KEY,
            timeout=self.settings.request_timeout_seconds,
            max_retries=0,
            http_client=self._http_client,
        )
        return ProviderErrorBoundary(
            OpenAIChatModel(
                MODEL_NAME,
                provider=OpenAICompatibleProvider(openai_client=client),
                profile=typing.cast("typing.Any", LOCAL_MODEL_PROFILE),
                settings=self._model_settings(),
            ),
            label="Local AI",
            recorded_name=AIProvider.LOCAL.value,
            unavailable=LocalAIUnavailableError,
            timeout=LocalAITimeoutError,
        )

    def _model_settings(self) -> ModelSettings | None:
        settings = ModelSettings()
        if self.settings.temperature is not None:
            settings["temperature"] = self.settings.temperature
        if self.settings.max_tokens is not None:
            settings["max_tokens"] = self.settings.max_tokens
        return settings or None

    async def health(self) -> AIStatus:
        """Ask the server's ``/health`` whether it can answer now."""
        try:
            url = self.base_url
        except ProviderConfigurationError as error:
            return self._status(AIStatusValue.NOT_CONFIGURED, str(error))
        if self._http_client is not None:
            return await self._check(self._http_client, url)
        async with httpx2.AsyncClient() as client:
            return await self._check(client, url)

    async def _check(self, client: httpx2.AsyncClient, url: str) -> AIStatus:
        try:
            response = await client.get(
                f"{url}/health",
                timeout=_HEALTH_TIMEOUT_SECONDS,
            )
        except httpx2.HTTPError:
            logger.info("Local AI health check failed")
            return self._status(
                AIStatusValue.UNAVAILABLE,
                "Local AI is not running.",
            )
        if response.status_code == _HTTP_OK:
            return self._status(
                AIStatusValue.READY,
                model=await self._loaded_model(client, url),
            )
        if response.status_code == _HTTP_SERVICE_UNAVAILABLE:
            return self._status(
                AIStatusValue.UNAVAILABLE,
                "Local AI is still loading its model.",
            )
        return self._status(AIStatusValue.UNAVAILABLE, "Local AI is not available.")

    async def _loaded_model(self, client: httpx2.AsyncClient, url: str) -> str | None:
        """Ask the server which model it loaded; None if it will not say."""
        headers = (
            {"Authorization": f"Bearer {self.settings.llama_api_key}"}
            if self.settings.llama_api_key
            else {}
        )
        try:
            response = await client.get(
                f"{url}/v1/models",
                headers=headers,
                timeout=_HEALTH_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            loaded = response.json()["data"][0]["id"]
        except (httpx2.HTTPError, ValueError, KeyError, IndexError, TypeError):
            return None
        return display_model_name(str(loaded))

    def _status(
        self,
        status: AIStatusValue,
        error: str | None = None,
        *,
        model: str | None = None,
    ) -> AIStatus:
        return AIStatus(provider=self.kind, status=status, model=model, error=error)


__all__ = [
    "LOCAL_MODEL_PROFILE",
    "LocalAIProvider",
    "LocalJsonSchemaTransformer",
    "display_model_name",
    "validate_local_url",
]
