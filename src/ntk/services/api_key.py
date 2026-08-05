from __future__ import annotations

import hashlib
import logging
import typing
from secrets import token_urlsafe

from ntk.models.api_key import ApiKey
from ntk.repositories.permission import PermissionRepository

if typing.TYPE_CHECKING:
    from ntk.repositories.api_key import ApiKeyRepository
    from ntk.repositories.permission import PermissionRepository

logger = logging.getLogger(__name__)


class ApiKeyService:
    def __init__(
        self,
        api_key_repo: ApiKeyRepository,
        permission_repo: PermissionRepository,
    ) -> None:
        """Service handles api keys.

        :param api_key_repo: API key repo
        :param permissions_repo: permissions repo
        """
        self.api_key_repo = api_key_repo
        self.permission_repo = permission_repo

    def revoke_api_key(self, plaintext_key: str) -> ApiKey | None:
        """Revoke api key.

        :param plaintext_key: plaintext key to filter by
        :return: revoked key model or None if not found
        """
        key_hash = self._hash_api_key(plaintext_key)
        return self.api_key_repo.revoke(key_hash)

    def get_api_keys(self, plaintext_key: str | None = None) -> list[ApiKey]:
        """Get api keys.

        :param plaintext_key: optional plaintext key to filter by
        :return: list of api keys
        """
        if plaintext_key:
            key_hash = self._hash_api_key(plaintext_key)
            api_key = self.api_key_repo.get_by_hash(key_hash)
            return [api_key] if api_key else []
        return list(self.api_key_repo.get_all())

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
        api_key = ApiKey(
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
