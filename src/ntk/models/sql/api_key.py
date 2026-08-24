# noqa: I002
"""SQL models for API keys and permissions."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel


class APIKeyPermission(SQLModel, table=True):
    """Link permissions and API keys in a many-to-many relationship."""

    __tablename__ = "api_key_permission"

    api_key_id: UUID = Field(foreign_key="api_key.id", primary_key=True)
    permission_id: UUID = Field(foreign_key="permission.id", primary_key=True)


class Permission(SQLModel, table=True):
    """An authorization permission assignable to API keys."""

    __tablename__ = "permission"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True, unique=True)
    api_keys: list["APIKey"] = Relationship(
        back_populates="permissions",
        link_model=APIKeyPermission,
    )


class APIKey(SQLModel, table=True):
    """A hashed API key and its authorization state."""

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
        sa_relationship_kwargs={"lazy": "selectin"},  # codespell:ignore-line
    )

    def has_permission(self, permission_name: str) -> bool:
        """Return whether this key has the named permission."""
        return any(
            permission.name == permission_name for permission in self.permissions
        )
