from __future__ import annotations

import typing

from fastapi import Depends, Header, HTTPException

from ntk.database.db import get_session
from ntk.repositories.api_key_repo import APIKeyRepo
from ntk.repositories.permission_repo import PermissionRepo
from ntk.services.api_key_service import APIKeyService

if typing.TYPE_CHECKING:
    from ntk.models.api_key import APIKey


def get_api_key_service() -> APIKeyService:
    """Dependency to get the APIKeyService instance."""
    session = next(get_session())
    repo = APIKeyRepo(session)
    permission_repo = PermissionRepo(session)
    return APIKeyService(repo, permission_repo)


def get_api_key(
    authorization: str = Header(...),
    api_key_service: APIKeyService = Depends(get_api_key_service),  # noqa: B008
) -> APIKey:
    """Dependency to get the API key from the request header.

    :param authorization: Authorization header
    :param api_key_service: APIKeyService instance
    :return: APIKey model
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing Authorization header",
        )
    raw_key = authorization[len("Bearer ") :]
    try:
        return api_key_service.authenticate(raw_key)
    except ValueError as err:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired API key",
        ) from err


def require_permission(required_permission: str) -> typing.Callable[..., APIKey]:
    """Dependency to check if the user has the required permission.

    :param required_permission: The permission required to access the endpoint.
    :return: A dependency function that checks for the required permission.
    """

    def permission_checker(api_key: APIKey = Depends(get_api_key)) -> APIKey:  # noqa: B008
        if not api_key.has_permission(required_permission):
            raise HTTPException(
                status_code=403,
                detail=f"Permission '{required_permission}' required",
            )
        return api_key

    return permission_checker


def require_any_permission(permissions: list[str]) -> typing.Callable[..., APIKey]:
    """Dependency to check if the user has any of the required permissions.

    :param permissions: List of permissions required to access the endpoint.
    :return: A dependency function that checks for any of the required permissions.
    """

    def permission_checker(api_key: APIKey = Depends(get_api_key)) -> APIKey:  # noqa: B008
        if not any(api_key.has_permission(permission) for permission in permissions):
            raise HTTPException(
                status_code=403,
                detail=f"At least one of the permissions '{', '.join(permissions)}' required",  # noqa: E501
            )
        return api_key

    return permission_checker
