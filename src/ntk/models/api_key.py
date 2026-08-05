# noqa: I002
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel


class APIKeyPermission(SQLModel, table=True):
    """Links Permission and ApiKey Models in many-to-many relationship."""

    __tablename__ = "api_key_permission"

    api_key_id: UUID = Field(foreign_key="api_key.id", primary_key=True)
    permission_id: UUID = Field(foreign_key="permission.id", primary_key=True)


class Permission(SQLModel, table=True):
    """Permission model."""

    __tablename__ = "permission"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True, unique=True)
    api_keys: list["APIKey"] = Relationship(
        back_populates="permissions",
        link_model=APIKeyPermission,
    )


class APIKey(SQLModel, table=True):
    """APIKey Model."""

    __tablename__ = "api_key"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    api_key_hash: str
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = Field(default=None)
    last_used_at: datetime | None = Field(default=None)
    revoked_at: datetime | None = Field(default=None)
    permissions: list["Permission"] = Relationship(
        back_populates="api_keys",
        link_model=APIKeyPermission,
        # always load permissions when loading api keys to avoid lazy loading issues
        sa_relationship_kwargs={"lazy": "selectin"},  # codespell:ignore-line
    )

    def has_permission(self, permission_name: str) -> bool:
        """Check if the API key has a specific permission.

        :param permission_name: Name of the permission to check
        :return: True if the API key has the permission, False otherwise
        """
        return any(
            permission.name == permission_name for permission in self.permissions
        )
