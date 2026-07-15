from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.database import get_session
from mycrm.modules.identity.dependencies import CurrentUser
from mycrm.modules.workspaces.application import (
    WorkspaceNotAccessibleError,
    resolve_member_workspace,
)
from mycrm.modules.workspaces.domain import WorkspaceContext


async def get_workspace_context(
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    workspace_id: Annotated[UUID, Header(alias="X-Workspace-ID")],
) -> WorkspaceContext:
    try:
        return await resolve_member_workspace(session, user, workspace_id)
    except WorkspaceNotAccessibleError as exc:
        raise HTTPException(status_code=404, detail="Workspace not found") from exc


CurrentWorkspace = Annotated[WorkspaceContext, Depends(get_workspace_context)]
