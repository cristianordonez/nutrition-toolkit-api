from __future__ import annotations

import hashlib
import logging
import typing
from datetime import UTC, datetime
from secrets import token_urlsafe

from ntk.models.sql.api_key import APIKey
from ntk.repositories.permission_repo import PermissionRepo

if typing.TYPE_CHECKING:
    from ntk.repositories.api_key_repo import APIKeyRepo
    from ntk.repositories.permission_repo import PermissionRepo

logger = logging.getLogger(__name__)


class APIKeyService:
    def __init__(
        self,
        api_key_repo: APIKeyRepo,
        permission_repo: PermissionRepo,
    ) -> None:
        """Service handles api keys.

        :param api_key_repo: API key repo
        :param permissions_repo: permissions repo
        """
        self.api_key_repo = api_key_repo
        self.permission_repo = permission_repo

    def authenticate(self, plaintext_key: str) -> APIKey:
        """Authenticate api key.

        :param plaintext_key: plaintext key to authenticate
        :return: api key model
        """
        key_hash = self._hash_api_key(plaintext_key)
        api_key = self.api_key_repo.get_by_hash(key_hash)
        if api_key is None:
            msg = "Invalid API key"
            raise ValueError(msg)
        if not api_key.active:
            msg = "API key is revoked"
            raise ValueError(msg)
        if api_key.expires_at is not None and api_key.expires_at < datetime.now(UTC):
            msg = "API key has expired"
            raise ValueError(msg)
        self.api_key_repo.update_last_used(api_key)
        return api_key

    def revoke_api_key(self, plaintext_key: str) -> APIKey | None:
        """Revoke api key.

        :param plaintext_key: plaintext key to filter by
        :return: revoked key model or None if not found
        """
        key_hash = self._hash_api_key(plaintext_key)
        return self.api_key_repo.revoke(key_hash)

    def get_api_keys(self, plaintext_key: str | None = None) -> list[APIKey]:
        """Get api keys.

        :param plaintext_key: optional plaintext key to filter by
        :return: list of api keys
        """
        if plaintext_key:
            key_hash = self._hash_api_key(plaintext_key)
            api_key = self.api_key_repo.get_by_hash(key_hash)
            return [api_key] if api_key else []
        return list(self.api_key_repo.get_all())

    def revoke_permission(self, api_key: APIKey, permission: str) -> None:
        """Revoke permission from api key.

        :param api_key: api key model
        :param permission: permission name to revoke
        """
        permission_model = self.permission_repo.get_by_name(permission)
        if not permission_model:
            msg = f"Permission '{permission}' not found in database."
            raise ValueError(msg)
        logger.info(
            "Revoking permission '%s' from api key '%s'",
            permission,
            api_key.name,
        )
        self.permission_repo.remove_permission_from_api_key(
            api_key.id,
            permission_model.id,
        )

    def grant_permission(self, api_key: APIKey, permission: str) -> None:
        """Grant permission to api key.

        :param api_key: api key model
        :param permission: permission name to grant
        """
        permission_model = self.permission_repo.get_by_name(permission)
        if not permission_model:
            msg = f"Permission '{permission}' not found in database."
            raise ValueError(msg)
        logger.info(
            "Granting permission '%s' to api key '%s'",
            permission,
            api_key.name,
        )
        self.permission_repo.add_permission_to_api_key(
            api_key.id,
            permission_model.id,
        )

    def create(
        self,
        name: str,
        permissions: list[str],
    ) -> str:
        """Create new api key.

        :param name: Name of the API key
        :param permissions: List of permissions for the API key
        :return: plaintext key
        """
        plaintext_key = self._generate_api_key()
        logger.debug("Generated API Key: %s", plaintext_key)
        key_hash = self._hash_api_key(plaintext_key)
        permission_models = self.permission_repo.get_by_names(permissions)
        logger.debug("Matching Permissions: %s", permissions)
        if len(permission_models) == 0:
            msg = f"Provided permissions not found in database: {permissions}"
            raise ValueError(msg)
        api_key = APIKey(
            name=name,
            api_key_hash=key_hash,
            permissions=permission_models,
        )
        self.api_key_repo.create(api_key)
        return plaintext_key

    @staticmethod
    def _generate_api_key() -> str:
        """Create random text key."""
        return str(token_urlsafe(32))

    @staticmethod
    def _hash_api_key(plaintext_key: str) -> str:
        """Hash api key.

        :param plaintext_key: key to hash
        :return: hashed api key
        """
        return hashlib.sha256(plaintext_key.encode("utf-8")).hexdigest()
