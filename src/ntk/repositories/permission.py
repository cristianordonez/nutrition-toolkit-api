from __future__ import annotations

from sqlmodel import Session, select

from ntk.models import Permission


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
