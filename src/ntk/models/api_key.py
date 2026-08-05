# noqa: I002
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel


class ApiKeyPermission(SQLModel, table=True):
    """Links Permission and ApiKey Models in many-to-many relationship."""

    __tablename__ = "api_key_permission"

    api_key_id: UUID = Field(foreign_key="api_key.id", primary_key=True)
    permission_id: UUID = Field(foreign_key="permission.id", primary_key=True)


class Permission(SQLModel, table=True):
    """Permission model."""

    __tablename__ = "permission"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True, unique=True)
    api_keys: list["ApiKey"] = Relationship(
        back_populates="permissions",
        link_model=ApiKeyPermission,
    )


class ApiKey(SQLModel, table=True):
    """ApiKey Model."""

    __tablename__ = "api_key"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    api_key_hash: str
    active: bool = True
    permissions: list["Permission"] = Relationship(
        back_populates="api_keys",
        link_model=ApiKeyPermission,
        # always load permissions when loading api keys to avoid lazy loading issues
        sa_relationship_kwargs={"lazy": "selectin"},  # codespell:ignore-line
    )
