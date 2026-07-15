from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from mycrm.core.database import Base
from mycrm.modules.crm_shared import RecordStatus


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_companies_status"),
        UniqueConstraint("workspace_id", "id", name="uq_companies_workspace_id"),
        Index("ix_companies_workspace_created", "workspace_id", "created_at", "id"),
        Index("ix_companies_workspace_name", "workspace_id", "name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200))
    website: Mapped[str | None] = mapped_column(String(2048))
    industry: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[RecordStatus] = mapped_column(
        Enum(
            RecordStatus,
            name="company_record_status",
            native_enum=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=RecordStatus.ACTIVE,
        server_default=RecordStatus.ACTIVE.value,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
