from __future__ import annotations

import logging
import typing

from sqlmodel import Session, delete, select

from ntk.defaults import DEFAULT_PERMISSIONS
from ntk.models import ApiKeyPermission, Permission

if typing.TYPE_CHECKING:
    from uuid import UUID

logger = logging.getLogger(__name__)


class PermissionRepository:
    def __init__(self, session: Session) -> None:
        """Handle API key permissions.

        :param session: Database session
        """
        self.session = session

    def get_by_name(self, name: str) -> Permission | None:
        """Get permission info by name.

        :param name: name of string
        :return: pydantic model
        """
        statement = select(Permission).where(Permission.name == name)
        return self.session.exec(statement).first()

    def get_by_names(self, names: list[str]) -> list[Permission]:
        """Get permission info by list of names.

        :param names: list of names
        :return: pydantic models
        """
        statement = select(Permission).where(Permission.name.in_(names))  # ty: ignore[unresolved-attribute]
        return self.session.exec(statement).all()  # ty: ignore[invalid-return-type]

    def list_all(self) -> list[Permission]:
        """List all permissions.

        :return: list of models
        """
        statement = select(Permission).order_by(Permission.name)
        return list(self.session.exec(statement))

    def create(self, permission: Permission) -> Permission:
        """Create permission in database.

        :param permission: model
        :return: echo created permission
        """
        self.session.add(permission)
        self.session.commit()
        self.session.refresh(permission)
        return permission

    def seed_defaults(self) -> None:
        """Seed default permissions."""
        existing = {
            permission.name
            for permission in self.session.exec(select(Permission)).all()
        }
        permissions = [
            Permission(name=name)
            for name in DEFAULT_PERMISSIONS
            if name not in existing
        ]
        if permissions:
            self.session.add_all(permissions)
            self.session.commit()

    def remove_permission_from_api_key(
        self,
        api_key_id: UUID,
        permission_id: UUID,
    ) -> None:
        """Remove permission from database.

        :param api_key_id: UUID for API key from which to remove permission
        :param permission_id: UUID for permission to remove
        """
        statement = delete(ApiKeyPermission).where(
            ApiKeyPermission.api_key_id == api_key_id,  # ty: ignore[invalid-argument-type]
            ApiKeyPermission.permission_id == permission_id,  # ty: ignore[invalid-argument-type]
        )
        self.session.exec(statement)
        self.session.commit()

    def add_permission_to_api_key(
        self,
        api_key_id: UUID,
        permission_id: UUID,
    ) -> None:
        """Add permission to database.

        :param api_key_id: UUID for API key to which to add permission
        :param permission_id: UUID for permission to add
        """
        statement = select(ApiKeyPermission).where(
            ApiKeyPermission.api_key_id == api_key_id,
            ApiKeyPermission.permission_id == permission_id,
        )
        existing = self.session.exec(statement).first()
        if existing:
            logger.debug(
                "Permission '%s' already exists for API key '%s'",
                permission_id,
                api_key_id,
            )
            return
        api_key_permission = ApiKeyPermission(
            api_key_id=api_key_id,
            permission_id=permission_id,
        )
        self.session.add(api_key_permission)
        self.session.commit()
