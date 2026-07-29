from __future__ import annotations

import hashlib
import typing
from secrets import token_urlsafe

from ntk.models.api_key import ApiKey, Permission

if typing.TYPE_CHECKING:
    from ntk.controllers.key.create import CreateKeyOptions
    from ntk.repositories.api_key import ApiKeyRepository


class ApiKeyService:
    def __init__(self, repository: ApiKeyRepository) -> None:
        """Service handles api keys.

        :param repository: API key repo
        """
        self.repository = repository

    def create(
        self,
        request: CreateKeyOptions,
        permissions: list[Permission],
    ) -> str:
        """Create new api key.

        :param request: Options provided to controller
        :return: plaintext key
        """
        plaintext_key = self._generate_api_key()
        key_hash = self._hash_api_key(plaintext_key)
        api_key = ApiKey(
            name=request.name,
            api_key_hash=key_hash,
            permissions=permissions,
        )
        self.repository.create(api_key)
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
