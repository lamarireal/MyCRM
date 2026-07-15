from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from mycrm.core.database import Base
from mycrm.modules.workspaces.domain import (
    MembershipStatus,
    WorkspaceKind,
    WorkspaceRole,
    WorkspaceStatus,
)


class Workspace(Base):
    __tablename__ = "workspaces"
    __table_args__ = (
        CheckConstraint("kind IN ('private', 'team', 'demo')", name="ck_workspaces_kind"),
        CheckConstraint(
            "status IN ('active', 'read_only', 'resetting', 'disabled')",
            name="ck_workspaces_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    kind: Mapped[WorkspaceKind] = mapped_column(
        Enum(
            WorkspaceKind,
            name="workspace_kind",
            native_enum=False,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    status: Mapped[WorkspaceStatus] = mapped_column(
        Enum(
            WorkspaceStatus,
            name="workspace_status",
            native_enum=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=WorkspaceStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"
    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'admin', 'member', 'viewer', 'demo_visitor')",
            name="ck_workspace_memberships_role",
        ),
        CheckConstraint(
            "status IN ('active', 'suspended')",
            name="ck_workspace_memberships_status",
        ),
        UniqueConstraint("workspace_id", "user_id", name="uq_membership_workspace_user"),
        Index("ix_workspace_memberships_user_id", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[WorkspaceRole] = mapped_column(
        Enum(
            WorkspaceRole,
            name="workspace_role",
            native_enum=False,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    status: Mapped[MembershipStatus] = mapped_column(
        Enum(
            MembershipStatus,
            name="membership_status",
            native_enum=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=MembershipStatus.ACTIVE,
        server_default=MembershipStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DemoSession(Base):
    __tablename__ = "demo_sessions"
    __table_args__ = (Index("ix_demo_sessions_workspace_expires", "workspace_id", "expires_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    session_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
