"""Add workspace-scoped tasks, activities, and notes.

Revision ID: 20260715_0007
Revises: 20260715_0006
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_0007"
down_revision: str | None = "20260715_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _crm_relationships(prefix: str) -> list[sa.ForeignKeyConstraint]:
    return [
        sa.ForeignKeyConstraint(
            ["workspace_id", "company_id"],
            ["companies.workspace_id", "companies.id"],
            name=f"fk_{prefix}_company_same_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            name=f"fk_{prefix}_contact_same_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "deal_id"],
            ["deals.workspace_id", "deals.id"],
            name=f"fk_{prefix}_deal_same_workspace",
            ondelete="RESTRICT",
        ),
    ]


def upgrade() -> None:
    op.create_unique_constraint("uq_deals_workspace_id", "deals", ["workspace_id", "id"])
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("deal_id", sa.Uuid(), nullable=True),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", sa.String(6), server_default="medium", nullable=False),
        sa.Column("status", sa.String(11), server_default="todo", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('todo', 'in_progress', 'done', 'cancelled', 'archived')",
            name="ck_tasks_status",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'urgent')", name="ck_tasks_priority"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="RESTRICT"),
        *_crm_relationships("tasks"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_workspace_due", "tasks", ["workspace_id", "due_at", "id"])
    op.create_index("ix_tasks_workspace_status", "tasks", ["workspace_id", "status"])
    op.create_index("ix_tasks_workspace_assignee", "tasks", ["workspace_id", "assignee_id"])

    op.create_table(
        "activities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("deal_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("activity_type", sa.String(12), nullable=False),
        sa.Column("source", sa.String(6), server_default="human", nullable=False),
        sa.Column("summary", sa.String(240), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "activity_type IN ('call', 'meeting', 'email', 'stage_change', 'task', 'other')",
            name="ck_activities_type",
        ),
        sa.CheckConstraint(
            "source IN ('human', 'rule', 'ai', 'system')", name="ck_activities_source"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        *_crm_relationships("activities"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_activities_workspace_occurred",
        "activities",
        ["workspace_id", "occurred_at", "id"],
    )
    op.create_index("ix_activities_workspace_deal", "activities", ["workspace_id", "deal_id"])

    op.create_table(
        "notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("deal_id", sa.Uuid(), nullable=True),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("normalized_body", sa.Text(), nullable=True),
        sa.Column("status", sa.String(8), server_default="active", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_notes_status"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
        *_crm_relationships("notes"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notes_workspace_updated", "notes", ["workspace_id", "updated_at", "id"])
    op.create_index("ix_notes_workspace_deal", "notes", ["workspace_id", "deal_id"])


def downgrade() -> None:
    op.drop_table("notes")
    op.drop_table("activities")
    op.drop_table("tasks")
    op.drop_constraint("uq_deals_workspace_id", "deals", type_="unique")
