"""The user's own API token, kept in the platform credential store.

Deliberately not in the application's SQLite database. That file is unencrypted
database in the application data directory: anything that can read the
user's files can read it, and it is copied wholesale into any backup of that
directory. A token belongs in the OS keychain (Keychain on macOS,
Secret Service on Linux, Credential Locker on Windows), which is what
``keyring`` wraps. The settings row stores only whether a cloud model is
enabled, never the secret itself.
"""

from __future__ import annotations

import logging

import keyring
from keyring.errors import KeyringError

logger = logging.getLogger(__name__)

#: Identifies this app's entries in the platform credential store.
SERVICE_NAME = "NutritionToolkit"

#: The account name the token is filed under in the credential store. It is
#: a lookup key, not a secret -- the secret is what the store returns for it.
CLOUD_MODEL_TOKEN = "cloud-model-api-token"  # noqa: S105


def get_cloud_token() -> str:
    """Return the stored token, or an empty string when there is none.

    A locked, missing, or unavailable keychain is reported as "no token"
    rather than raised: the caller's next step is to fall back to the
    on-device model, which is the right outcome either way.
    """
    try:
        return keyring.get_password(SERVICE_NAME, CLOUD_MODEL_TOKEN) or ""
    except KeyringError:
        logger.warning("Could not read the credential store", exc_info=True)
        return ""


def set_cloud_token(token: str) -> None:
    """Store the user's token, or clear it when given an empty string."""
    if not token:
        clear_cloud_token()
        return
    keyring.set_password(SERVICE_NAME, CLOUD_MODEL_TOKEN, token)


def clear_cloud_token() -> None:
    """Remove the stored token. Removing one that is absent is not an error."""
    try:
        keyring.delete_password(SERVICE_NAME, CLOUD_MODEL_TOKEN)
    except KeyringError:
        logger.debug("No stored token to remove", exc_info=True)


def has_cloud_token() -> bool:
    """Report whether a token is stored, without returning it.

    Lets the UI and the CLI describe the state without moving the secret
    through a subprocess boundary and into a log.
    """
    return bool(get_cloud_token())


__all__ = [
    "CLOUD_MODEL_TOKEN",
    "SERVICE_NAME",
    "clear_cloud_token",
    "get_cloud_token",
    "has_cloud_token",
    "set_cloud_token",
]
