"""Add safe stage archival and immutable audit records.

Revision ID: 20260718_0008
Revises: 20260715_0007
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260718_0008"
down_revision: str | None = "20260715_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_pipeline_stages_position", "pipeline_stages", type_="check")
    op.alter_column("pipeline_stages", "position", existing_type=sa.Integer(), nullable=True)
    op.create_check_constraint(
        "ck_pipeline_stages_position",
        "pipeline_stages",
        "position IS NULL OR position >= 1",
    )
    op.create_table(
        "audit_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(6), server_default="human", nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("before_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('human', 'rule', 'ai', 'system')", name="ck_audit_records_source"
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_records_workspace_created",
        "audit_records",
        ["workspace_id", "created_at", "id"],
    )
    op.create_index(
        "ix_audit_records_workspace_entity",
        "audit_records",
        ["workspace_id", "entity_type", "entity_id"],
    )
    op.execute(
        """
        CREATE FUNCTION prevent_audit_record_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit records are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_records_append_only
        BEFORE UPDATE OR DELETE ON audit_records
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_record_mutation()
        """
    )


def downgrade() -> None:
    op.drop_table("audit_records")
    op.execute("DROP FUNCTION prevent_audit_record_mutation()")
    op.drop_constraint("ck_pipeline_stages_position", "pipeline_stages", type_="check")
    op.alter_column("pipeline_stages", "position", existing_type=sa.Integer(), nullable=False)
    op.create_check_constraint("ck_pipeline_stages_position", "pipeline_stages", "position >= 1")
