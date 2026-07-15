from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.config import Settings, get_settings
from mycrm.core.database import get_session
from mycrm.modules.identity.dependencies import CurrentUser
from mycrm.modules.workspaces.application import list_accessible_workspaces
from mycrm.modules.workspaces.dependencies import CurrentWorkspace
from mycrm.modules.workspaces.domain import WorkspaceContext, WorkspaceRole
from mycrm.modules.workspaces.models import Workspace

router = APIRouter()


class DemoCapabilitiesResponse(BaseModel):
    enabled: bool
    read_only: bool
    synthetic_data_only: bool = True
    external_side_effects_enabled: bool = False


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    kind: str
    status: str
    role: WorkspaceRole

    @classmethod
    def from_model(cls, workspace: Workspace, role: WorkspaceRole) -> "WorkspaceResponse":
        return cls(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            kind=workspace.kind.value,
            status=workspace.status.value,
            role=role,
        )


class WorkspaceContextResponse(BaseModel):
    workspace_id: UUID
    actor_id: UUID | None
    role: WorkspaceRole
    kind: str
    status: str
    can_write: bool

    @classmethod
    def from_context(cls, context: WorkspaceContext) -> "WorkspaceContextResponse":
        return cls(
            workspace_id=context.workspace_id,
            actor_id=context.actor_id,
            role=context.role,
            kind=context.kind.value,
            status=context.status.value,
            can_write=context.can_write,
        )


@router.get("/demo/capabilities", response_model=DemoCapabilitiesResponse, tags=["demo"])
async def demo_capabilities(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DemoCapabilitiesResponse:
    return DemoCapabilitiesResponse(
        enabled=settings.demo_enabled, read_only=settings.demo_read_only
    )


@router.get("/workspaces", response_model=list[WorkspaceResponse], tags=["workspaces"])
async def list_workspaces(
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[WorkspaceResponse]:
    workspaces = await list_accessible_workspaces(session, user)
    return [
        WorkspaceResponse.from_model(workspace, membership.role)
        for workspace, membership in workspaces
    ]


@router.get("/workspaces/current", response_model=WorkspaceContextResponse, tags=["workspaces"])
async def current_workspace(context: CurrentWorkspace) -> WorkspaceContextResponse:
    return WorkspaceContextResponse.from_context(context)
