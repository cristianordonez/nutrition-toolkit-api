from __future__ import annotations

import typing

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ntk.database.db import get_session
from ntk.repositories.api_key_repo import APIKeyRepo
from ntk.repositories.permission_repo import PermissionRepo
from ntk.services.api_key_service import APIKeyService
from ntk.services.redis_service import redis

if typing.TYPE_CHECKING:
    from collections.abc import Awaitable

    from ntk.models.api_key import APIKey

bearer = HTTPBearer(auto_error=False)


def get_api_key_service() -> APIKeyService:
    """Dependency to get the APIKeyService instance."""
    session = next(get_session())
    repo = APIKeyRepo(session)
    permission_repo = PermissionRepo(session)
    return APIKeyService(repo, permission_repo)


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> APIKey:
    """Dependency to get the API key from the request header.

    :param authorization: Authorization header
    :param api_key_service: APIKeyService instance
    :return: APIKey model
    """
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
        )
    try:
        raw_key = credentials.credentials
        api_key_service = get_api_key_service()
        return api_key_service.authenticate(raw_key)
    except ValueError as err:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired API key",
        ) from err


def require_permission(
    required_permission: str,
) -> typing.Callable[..., Awaitable[APIKey]]:
    """Dependency to check if the user has the required permission.

    :param required_permission: The permission required to access the endpoint.
    :return: A dependency function that checks for the required permission.
    """

    async def permission_checker(
        api_key: APIKey = Depends(verify_api_key),
    ) -> APIKey:
        if not api_key.has_permission(required_permission):
            raise HTTPException(
                status_code=403,
                detail=f"Permission '{required_permission}' required",
            )
        return api_key

    return permission_checker


def require_any_permission(
    permissions: list[str],
) -> typing.Callable[..., Awaitable[APIKey]]:
    """Dependency to check if the user has any of the required permissions.

    :param permissions: List of permissions required to access the endpoint.
    :return: A dependency function that checks for any of the required permissions.
    """

    async def permission_checker(
        api_key: APIKey = Depends(verify_api_key),
    ) -> APIKey:
        if not any(api_key.has_permission(permission) for permission in permissions):
            raise HTTPException(
                status_code=403,
                detail=f"At least one of the permissions '{', '.join(permissions)}' required",  # noqa: E501
            )
        return api_key

    return permission_checker


def rate_limit(limit: int, window: int = 60) -> typing.Callable[..., Awaitable[None]]:
    """Dependency to limit number of requests per minute.

    :param limit: number of requests allowed per minute
    :param window: number of seconds before counter resets
    :return: A dependency function that enforces number of requests, using redis
    """

    async def rate_limiter(
        api_key: APIKey = Depends(verify_api_key),
    ) -> None:
        client_id = f"{api_key.name}-{api_key.id}"
        key = f"rate_limit:{client_id}"
        count = await redis.incr(key)  # ty: ignore[invalid-await]
        if count == 1:
            await redis.expire(key, window)
        if count > limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return rate_limiter
