from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from mycrm.core.database import Base


class DealStatus(StrEnum):
    OPEN = "open"
    WON = "won"
    LOST = "lost"
    ARCHIVED = "archived"


class Deal(Base):
    __tablename__ = "deals"
    __table_args__ = (
        CheckConstraint("amount IS NULL OR amount >= 0", name="ck_deals_amount"),
        CheckConstraint("probability BETWEEN 0 AND 100", name="ck_deals_probability"),
        CheckConstraint("status IN ('open', 'won', 'lost', 'archived')", name="ck_deals_status"),
        UniqueConstraint("workspace_id", "id", name="uq_deals_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "company_id"],
            ["companies.workspace_id", "companies.id"],
            name="fk_deals_company_same_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            name="fk_deals_contact_same_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "pipeline_id"],
            ["pipelines.workspace_id", "pipelines.id"],
            name="fk_deals_pipeline_same_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "pipeline_id", "stage_id"],
            [
                "pipeline_stages.workspace_id",
                "pipeline_stages.pipeline_id",
                "pipeline_stages.id",
            ],
            name="fk_deals_stage_same_pipeline_workspace",
            ondelete="RESTRICT",
        ),
        Index("ix_deals_workspace_created", "workspace_id", "created_at", "id"),
        Index("ix_deals_workspace_pipeline_stage", "workspace_id", "pipeline_id", "stage_id"),
        Index("ix_deals_workspace_company", "workspace_id", "company_id"),
        Index("ix_deals_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    pipeline_id: Mapped[UUID]
    stage_id: Mapped[UUID]
    company_id: Mapped[UUID | None]
    contact_id: Mapped[UUID | None]
    title: Mapped[str] = mapped_column(String(200))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR", server_default="EUR")
    probability: Mapped[int]
    expected_close_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[DealStatus] = mapped_column(
        Enum(
            DealStatus,
            name="deal_status",
            native_enum=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=DealStatus.OPEN,
        server_default=DealStatus.OPEN.value,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
