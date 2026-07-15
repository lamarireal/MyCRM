from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.modules.identity.models import User
from mycrm.modules.workspaces.domain import (
    MembershipStatus,
    WorkspaceContext,
    WorkspaceKind,
    WorkspaceRole,
    WorkspaceStatus,
)
from mycrm.modules.workspaces.models import Workspace, WorkspaceMembership


class WorkspaceNotAccessibleError(Exception):
    pass


async def list_accessible_workspaces(
    session: AsyncSession, user: User
) -> list[tuple[Workspace, WorkspaceMembership]]:
    result = await session.execute(
        select(Workspace, WorkspaceMembership)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(
            WorkspaceMembership.user_id == user.id,
            WorkspaceMembership.status == MembershipStatus.ACTIVE,
            Workspace.status != WorkspaceStatus.DISABLED,
        )
        .order_by(Workspace.created_at)
    )
    return list(result.tuples())


async def resolve_member_workspace(
    session: AsyncSession, user: User, workspace_id: UUID
) -> WorkspaceContext:
    result = await session.execute(
        select(Workspace, WorkspaceMembership)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(
            Workspace.id == workspace_id,
            WorkspaceMembership.user_id == user.id,
            WorkspaceMembership.status == MembershipStatus.ACTIVE,
            Workspace.status != WorkspaceStatus.DISABLED,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise WorkspaceNotAccessibleError
    workspace, membership = row
    return WorkspaceContext(
        workspace_id=workspace.id,
        actor_id=user.id,
        role=membership.role,
        kind=workspace.kind,
        status=workspace.status,
    )


async def resolve_demo_workspace(session: AsyncSession, slug: str) -> WorkspaceContext:
    workspace = await session.scalar(
        select(Workspace).where(
            Workspace.slug == slug,
            Workspace.kind == WorkspaceKind.DEMO,
            Workspace.status.in_([WorkspaceStatus.ACTIVE, WorkspaceStatus.READ_ONLY]),
        )
    )
    if workspace is None:
        raise WorkspaceNotAccessibleError
    return WorkspaceContext(
        workspace_id=workspace.id,
        actor_id=None,
        role=WorkspaceRole.DEMO_VISITOR,
        kind=workspace.kind,
        status=workspace.status,
    )
