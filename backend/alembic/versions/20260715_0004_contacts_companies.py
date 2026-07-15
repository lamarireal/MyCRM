"""Add workspace-scoped companies and contacts.

Revision ID: 20260715_0004
Revises: 20260715_0003
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_0004"
down_revision: str | None = "20260715_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("website", sa.String(length=2048), nullable=True),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=8), server_default="active", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_companies_status"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_companies_workspace_id"),
    )
    op.create_index(
        "ix_companies_workspace_created",
        "companies",
        ["workspace_id", "created_at", "id"],
    )
    op.create_index("ix_companies_workspace_name", "companies", ["workspace_id", "name"])

    op.create_table(
        "contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("first_name", sa.String(length=120), nullable=False),
        sa.Column("last_name", sa.String(length=120), server_default="", nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("job_title", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=8), server_default="active", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_contacts_status"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "company_id"],
            ["companies.workspace_id", "companies.id"],
            name="fk_contacts_company_same_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_contacts_workspace_created", "contacts", ["workspace_id", "created_at", "id"]
    )
    op.create_index(
        "ix_contacts_workspace_name",
        "contacts",
        ["workspace_id", "last_name", "first_name"],
    )
    op.create_index("ix_contacts_workspace_email", "contacts", ["workspace_id", "email"])


def downgrade() -> None:
    op.drop_index("ix_contacts_workspace_email", table_name="contacts")
    op.drop_index("ix_contacts_workspace_name", table_name="contacts")
    op.drop_index("ix_contacts_workspace_created", table_name="contacts")
    op.drop_table("contacts")
    op.drop_index("ix_companies_workspace_name", table_name="companies")
    op.drop_index("ix_companies_workspace_created", table_name="companies")
    op.drop_table("companies")
