# noqa: INP001
"""
One-time setup script: creates the Databricks secret scope and stores the
Massive API key. Run this locally (with the Databricks CLI configured) or
from a notebook - never commit the resulting secret value anywhere.

Usage:
    python setup_secrets.py
"""

from __future__ import annotations

import getpass

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import workspace

w = WorkspaceClient()


w.secrets.create_scope(scope="database")
w.secrets.put_secret(
    scope="database",
    key="ntk-database-url",
    string_value=getpass.getpass("Paste your Lakebase URL: "),
)


w.secrets.put_acl(
    scope="database",
    principal="users",
    permission=workspace.AclPermission.READ,
)
