"""Add workspace-scoped sales pipelines and deals.

Revision ID: 20260715_0006
Revises: 20260715_0005
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_0006"
down_revision: str | None = "20260715_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_contacts_workspace_id", "contacts", ["workspace_id", "id"])
    op.create_table(
        "pipelines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(8), server_default="active", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_pipelines_status"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_pipelines_workspace_id"),
    )
    op.create_index("ix_pipelines_workspace_name", "pipelines", ["workspace_id", "name"])
    op.create_table(
        "pipeline_stages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("probability", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(4), server_default="open", nullable=False),
        sa.Column("status", sa.String(8), server_default="active", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("probability BETWEEN 0 AND 100", name="ck_pipeline_stages_probability"),
        sa.CheckConstraint("position >= 1", name="ck_pipeline_stages_position"),
        sa.CheckConstraint("outcome IN ('open', 'won', 'lost')", name="ck_pipeline_stages_outcome"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_pipeline_stages_status"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "pipeline_id"],
            ["pipelines.workspace_id", "pipelines.id"],
            name="fk_pipeline_stages_pipeline_same_workspace",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "pipeline_id", "id", name="uq_pipeline_stages_workspace_pipeline_id"
        ),
        sa.UniqueConstraint(
            "workspace_id", "pipeline_id", "position", name="uq_pipeline_stages_position"
        ),
    )
    op.create_index(
        "ix_pipeline_stages_workspace_pipeline",
        "pipeline_stages",
        ["workspace_id", "pipeline_id", "position"],
    )
    op.create_table(
        "deals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.Column("stage_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("currency", sa.String(3), server_default="EUR", nullable=False),
        sa.Column("probability", sa.Integer(), nullable=False),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(8), server_default="open", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("amount IS NULL OR amount >= 0", name="ck_deals_amount"),
        sa.CheckConstraint("probability BETWEEN 0 AND 100", name="ck_deals_probability"),
        sa.CheckConstraint("status IN ('open', 'won', 'lost', 'archived')", name="ck_deals_status"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "company_id"],
            ["companies.workspace_id", "companies.id"],
            name="fk_deals_company_same_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            name="fk_deals_contact_same_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "pipeline_id"],
            ["pipelines.workspace_id", "pipelines.id"],
            name="fk_deals_pipeline_same_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "pipeline_id", "stage_id"],
            ["pipeline_stages.workspace_id", "pipeline_stages.pipeline_id", "pipeline_stages.id"],
            name="fk_deals_stage_same_pipeline_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deals_workspace_created", "deals", ["workspace_id", "created_at", "id"])
    op.create_index(
        "ix_deals_workspace_pipeline_stage", "deals", ["workspace_id", "pipeline_id", "stage_id"]
    )
    op.create_index("ix_deals_workspace_company", "deals", ["workspace_id", "company_id"])
    op.create_index("ix_deals_workspace_status", "deals", ["workspace_id", "status"])


def downgrade() -> None:
    op.drop_table("deals")
    op.drop_table("pipeline_stages")
    op.drop_table("pipelines")
    op.drop_constraint("uq_contacts_workspace_id", "contacts", type_="unique")
