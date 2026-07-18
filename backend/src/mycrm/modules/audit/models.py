from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mycrm.core.database import Base


class AuditSource(StrEnum):
    HUMAN = "human"
    RULE = "rule"
    AI = "ai"
    SYSTEM = "system"


class AuditRecord(Base):
    __tablename__ = "audit_records"
    __table_args__ = (
        CheckConstraint(
            "source IN ('human', 'rule', 'ai', 'system')", name="ck_audit_records_source"
        ),
        Index("ix_audit_records_workspace_created", "workspace_id", "created_at", "id"),
        Index("ix_audit_records_workspace_entity", "workspace_id", "entity_type", "entity_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    source: Mapped[AuditSource] = mapped_column(
        Enum(
            AuditSource,
            name="audit_source",
            native_enum=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=AuditSource.HUMAN,
        server_default=AuditSource.HUMAN.value,
    )
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[UUID]
    before_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    after_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
