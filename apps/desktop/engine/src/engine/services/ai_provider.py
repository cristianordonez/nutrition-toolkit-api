"""Which model every agent in this engine runs on.

One decision, made in one place, so extraction and note generation cannot
disagree about where a resident's clinical data is sent.

On-device is the default and the fallback. A hosted model is used only when
the user has both switched it on in Settings and supplied their own API
token; missing either one silently means on-device, because the safe
direction for clinical data is to keep it on the machine.
"""

from __future__ import annotations

import logging
import typing

from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider

from engine.controllers.session import settings_session
from engine.models.settings import SETTINGS
from engine.repositories.settings_repo import SettingsRepo
from engine.services.credentials import get_cloud_token
from engine.services.local_model import resolve_model

if typing.TYPE_CHECKING:
    from pydantic_ai.models import Model

logger = logging.getLogger(__name__)

#: Where inference runs. "ollama" is on-device, "openai" is hosted.
Provider = typing.Literal["ollama", "openai"]

#: The hosted model used when the user opts in with their own token.
CLOUD_MODEL = "gpt-5.6-luna"


def configured_provider() -> Provider:
    """Return the provider the user's settings select.

    Falls back to on-device when the cloud is requested without a token,
    rather than failing: the note still gets written, just locally.
    """
    if not _cloud_requested():
        return "ollama"
    if not get_cloud_token():
        logger.warning(
            "Cloud model is enabled but no API token is stored; "
            "running on-device instead.",
        )
        return "ollama"
    return "openai"


def build_model(
    provider: Provider | None = None,
    *,
    cloud_model: str = CLOUD_MODEL,
) -> Model:
    """Build a model, defaulting to the one the settings select.

    Built on demand rather than at import so neither provider's
    prerequisites are needed merely to import the engine: on-device needs no
    API token, and hosted needs no Ollama daemon. Taking the provider as an
    argument also lets one process build both, which is what comparing them
    requires.

    ``cloud_model`` lets a caller name the hosted model suited to its task.
    The on-device model is not per-task: a device holds one downloaded model
    and every agent shares it.
    """
    if (provider or configured_provider()) == "openai":
        return OpenAIResponsesModel(
            cloud_model,
            provider=OpenAIProvider(api_key=get_cloud_token()),
        )
    model_name = resolve_model(override=SETTINGS.ollama_model)
    # Ollama serves the OpenAI-compatible API under /v1, and the provider
    # does not append it.
    base_url = f"{SETTINGS.ollama_host.rstrip('/')}/v1"
    return OpenAIChatModel(model_name, provider=OllamaProvider(base_url=base_url))


def _cloud_requested() -> bool:
    """Report whether the user switched the hosted model on.

    A settings database that cannot be read means "not requested": the
    on-device default is what a device with no stored preference should do.
    """
    try:
        with settings_session(None) as session:
            return SettingsRepo(session).get().use_cloud_model
    except Exception:
        logger.warning("Could not read user settings", exc_info=True)
        return False


__all__ = ["CLOUD_MODEL", "Provider", "build_model", "configured_provider"]
