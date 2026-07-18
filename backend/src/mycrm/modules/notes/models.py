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
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from mycrm.core.database import Base
from mycrm.modules.crm_shared import RecordStatus


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_notes_status"),
        ForeignKeyConstraint(
            ["workspace_id", "company_id"],
            ["companies.workspace_id", "companies.id"],
            name="fk_notes_company_same_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            name="fk_notes_contact_same_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "deal_id"],
            ["deals.workspace_id", "deals.id"],
            name="fk_notes_deal_same_workspace",
            ondelete="RESTRICT",
        ),
        Index("ix_notes_workspace_updated", "workspace_id", "updated_at", "id"),
        Index("ix_notes_workspace_deal", "workspace_id", "deal_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[UUID | None]
    contact_id: Mapped[UUID | None]
    deal_id: Mapped[UUID | None]
    author_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text)
    normalized_body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[RecordStatus] = mapped_column(
        Enum(
            RecordStatus,
            name="note_status",
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
