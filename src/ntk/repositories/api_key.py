from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from sqlmodel import Session

    from ntk.models.api_key import ApiKey


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
