"""The device user's own profile, stored in the settings database.

Nothing here is clinical data about a resident -- it describes the dietitian
using this device. It lives in its own SQLite file (``settings.db``) so that
the user's profile and the clinical record have independent lifetimes: the
facts database can be cleared, restored, or migrated without touching the
user's own settings, and vice versa.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint
from sqlalchemy.orm import registry
from sqlmodel import Field, SQLModel

settings_registry = registry()

SINGLETON_ID = 1


class SettingsBase(SQLModel, registry=settings_registry):
    """Base class for every table stored in the settings database.

    Holding its own registry keeps these tables out of ``SQLModel.metadata``,
    which the facts database uses. ``create_all`` against either database can
    therefore only ever build that database's own tables.
    """


class UserSettings(SettingsBase, table=True):
    """The dietitian using this device.

    A single-user desktop app, so this table holds exactly one row, pinned to
    ``SINGLETON_ID`` by a check constraint.
    """

    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint(f"id = {SINGLETON_ID}", name="ck_user_settings_singleton"),
    )

    id: int | None = Field(default=SINGLETON_ID, primary_key=True)
    full_name: str | None = Field(
        default=None,
        description="The dietitian's name, as it should appear on a note.",
    )
    credentials: str | None = Field(
        default=None,
        description="Professional credentials to sign notes with, e.g. 'RD, LDN'.",
    )
    # Facilities live in the facts database, so this stores the facility's
    # stable identifier rather than a foreign key -- the two SQLite files are
    # separate connections and cannot reference each other.
    default_facility_identifier: str | None = Field(
        default=None,
        description="facility_identifier of the facility to preselect.",
    )


__all__ = ["SINGLETON_ID", "SettingsBase", "UserSettings", "settings_registry"]
