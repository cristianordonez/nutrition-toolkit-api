from __future__ import annotations

import typing

from sqlmodel import select

from ntk.models.api_key import ApiKey

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlmodel import Session


class ApiKeyRepository:
    def __init__(self, session: Session) -> None:
        """Get api keys from database.

        :param session: database session
        """
        self.session = session

    def create(self, api_key: ApiKey) -> ApiKey:
        """Create api key in database.

        :param api_key: api key model
        :return: echo created key
        """
        self.session.add(api_key)
        self.session.commit()
        self.session.refresh(api_key)
        return api_key

    def get_by_hash(self, api_key_hash: str) -> ApiKey | None:
        """Get api key by hash.

        :param api_key_hash: hashed api key
        :return: api key model or None if not found
        """
        statement = select(ApiKey).where(ApiKey.api_key_hash == api_key_hash)
        return self.session.exec(statement).first()

    def get_all(self) -> Sequence[ApiKey]:
        """Get all api keys.

        :return: list of api key models
        """
        statement = select(ApiKey)
        return self.session.exec(statement).all()

    def get_by_name(self, name: str) -> ApiKey | None:
        """Get api key by name.

        :param name: name of api key
        :return: api key model or None if not found
        """
        statement = select(ApiKey).where(ApiKey.name == name)
        return self.session.exec(statement).first()
