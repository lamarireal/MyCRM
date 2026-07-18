from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from mycrm.core.database import Base


class ActivityType(StrEnum):
    CALL = "call"
    MEETING = "meeting"
    EMAIL = "email"
    STAGE_CHANGE = "stage_change"
    TASK = "task"
    OTHER = "other"


class ActivitySource(StrEnum):
    HUMAN = "human"
    RULE = "rule"
    AI = "ai"
    SYSTEM = "system"


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (
        CheckConstraint(
            "activity_type IN ('call', 'meeting', 'email', 'stage_change', 'task', 'other')",
            name="ck_activities_type",
        ),
        CheckConstraint("source IN ('human', 'rule', 'ai', 'system')", name="ck_activities_source"),
        ForeignKeyConstraint(
            ["workspace_id", "company_id"],
            ["companies.workspace_id", "companies.id"],
            name="fk_activities_company_same_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            name="fk_activities_contact_same_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "deal_id"],
            ["deals.workspace_id", "deals.id"],
            name="fk_activities_deal_same_workspace",
            ondelete="RESTRICT",
        ),
        Index("ix_activities_workspace_occurred", "workspace_id", "occurred_at", "id"),
        Index("ix_activities_workspace_deal", "workspace_id", "deal_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[UUID | None]
    contact_id: Mapped[UUID | None]
    deal_id: Mapped[UUID | None]
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    activity_type: Mapped[ActivityType] = mapped_column(
        Enum(
            ActivityType,
            name="activity_type",
            native_enum=False,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    source: Mapped[ActivitySource] = mapped_column(
        Enum(
            ActivitySource,
            name="activity_source",
            native_enum=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=ActivitySource.HUMAN,
        server_default=ActivitySource.HUMAN.value,
    )
    summary: Mapped[str] = mapped_column(String(240))
    details: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
