from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from mycrm.core.database import Base
from mycrm.modules.crm_shared import RecordStatus


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_contacts_status"),
        ForeignKeyConstraint(
            ["workspace_id", "company_id"],
            ["companies.workspace_id", "companies.id"],
            name="fk_contacts_company_same_workspace",
            ondelete="RESTRICT",
        ),
        Index("ix_contacts_workspace_created", "workspace_id", "created_at", "id"),
        Index("ix_contacts_workspace_name", "workspace_id", "last_name", "first_name"),
        Index("ix_contacts_workspace_email", "workspace_id", "email"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[UUID | None]
    first_name: Mapped[str] = mapped_column(String(120))
    last_name: Mapped[str] = mapped_column(String(120), default="", server_default="")
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    job_title: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[RecordStatus] = mapped_column(
        Enum(
            RecordStatus,
            name="contact_record_status",
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
