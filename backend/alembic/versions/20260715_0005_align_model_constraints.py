"""Align existing database nullability with model invariants.

Revision ID: 20260715_0005
Revises: 20260715_0004
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_0005"
down_revision: str | None = "20260715_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TIMESTAMP_COLUMNS = (
    ("auth_sessions", "created_at"),
    ("auth_sessions", "last_seen_at"),
    ("companies", "created_at"),
    ("companies", "updated_at"),
    ("contacts", "created_at"),
    ("contacts", "updated_at"),
    ("demo_sessions", "created_at"),
    ("demo_sessions", "last_seen_at"),
    ("users", "created_at"),
    ("users", "updated_at"),
    ("workspace_memberships", "created_at"),
    ("workspaces", "created_at"),
    ("workspaces", "updated_at"),
)


def upgrade() -> None:
    for table_name, column_name in _TIMESTAMP_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )
    op.alter_column(
        "workspaces",
        "status",
        existing_type=sa.String(length=10),
        type_=sa.String(length=9),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "workspaces",
        "status",
        existing_type=sa.String(length=9),
        type_=sa.String(length=10),
        existing_nullable=False,
    )
    for table_name, column_name in reversed(_TIMESTAMP_COLUMNS):
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )
