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
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from mycrm.core.database import Base
from mycrm.modules.crm_shared import RecordStatus


class StageOutcome(StrEnum):
    OPEN = "open"
    WON = "won"
    LOST = "lost"


class Pipeline(Base):
    __tablename__ = "pipelines"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_pipelines_status"),
        UniqueConstraint("workspace_id", "id", name="uq_pipelines_workspace_id"),
        Index("ix_pipelines_workspace_name", "workspace_id", "name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[RecordStatus] = mapped_column(
        Enum(
            RecordStatus,
            name="pipeline_record_status",
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


class PipelineStage(Base):
    __tablename__ = "pipeline_stages"
    __table_args__ = (
        CheckConstraint("probability BETWEEN 0 AND 100", name="ck_pipeline_stages_probability"),
        CheckConstraint("position IS NULL OR position >= 1", name="ck_pipeline_stages_position"),
        CheckConstraint("outcome IN ('open', 'won', 'lost')", name="ck_pipeline_stages_outcome"),
        CheckConstraint("status IN ('active', 'archived')", name="ck_pipeline_stages_status"),
        ForeignKeyConstraint(
            ["workspace_id", "pipeline_id"],
            ["pipelines.workspace_id", "pipelines.id"],
            name="fk_pipeline_stages_pipeline_same_workspace",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "workspace_id", "pipeline_id", "id", name="uq_pipeline_stages_workspace_pipeline_id"
        ),
        UniqueConstraint(
            "workspace_id", "pipeline_id", "position", name="uq_pipeline_stages_position"
        ),
        Index("ix_pipeline_stages_workspace_pipeline", "workspace_id", "pipeline_id", "position"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID]
    pipeline_id: Mapped[UUID]
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[int | None]
    probability: Mapped[int]
    outcome: Mapped[StageOutcome] = mapped_column(
        Enum(
            StageOutcome,
            name="stage_outcome",
            native_enum=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=StageOutcome.OPEN,
        server_default=StageOutcome.OPEN.value,
    )
    status: Mapped[RecordStatus] = mapped_column(
        Enum(
            RecordStatus,
            name="pipeline_stage_record_status",
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
