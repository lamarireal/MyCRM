from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.database import get_session
from mycrm.modules.activities.application import create_activity, get_activity, list_activities
from mycrm.modules.activities.models import Activity, ActivitySource, ActivityType
from mycrm.modules.crm_shared import (
    EntityNotFoundError,
    RelatedEntityNotFoundError,
    WorkspaceWriteForbiddenError,
)
from mycrm.modules.workspaces.dependencies import CurrentWorkspace

router = APIRouter(prefix="/activities", tags=["activities"])


class ActivityCreateRequest(BaseModel):
    activity_type: ActivityType
    summary: str = Field(min_length=1, max_length=240)
    details: str | None = Field(default=None, max_length=20_000)
    occurred_at: datetime
    company_id: UUID | None = None
    contact_id: UUID | None = None
    deal_id: UUID | None = None


class ActivityResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    company_id: UUID | None
    contact_id: UUID | None
    deal_id: UUID | None
    created_by_id: UUID | None
    activity_type: ActivityType
    source: ActivitySource
    summary: str
    details: str | None
    occurred_at: datetime
    created_at: datetime

    @classmethod
    def from_model(cls, activity: Activity) -> "ActivityResponse":
        return cls.model_validate(activity, from_attributes=True)


class ActivityPageResponse(BaseModel):
    items: list[ActivityResponse]
    next_cursor: UUID | None


def _http_error(exc: Exception) -> None:
    if isinstance(exc, EntityNotFoundError):
        raise HTTPException(status_code=404, detail="Activity or cursor not found") from exc
    if isinstance(exc, RelatedEntityNotFoundError):
        raise HTTPException(status_code=404, detail="Related CRM record not found") from exc
    if isinstance(exc, WorkspaceWriteForbiddenError):
        raise HTTPException(status_code=403, detail="Workspace is read-only") from exc
    raise exc


@router.post("", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
async def create(
    payload: ActivityCreateRequest,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ActivityResponse:
    try:
        activity = await create_activity(session, context, **payload.model_dump())
    except Exception as exc:
        _http_error(exc)
        raise
    return ActivityResponse.from_model(activity)


@router.get("", response_model=ActivityPageResponse)
async def list_all(
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
    company_id: UUID | None = None,
    contact_id: UUID | None = None,
    deal_id: UUID | None = None,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ActivityPageResponse:
    try:
        page = await list_activities(
            session,
            context,
            company_id=company_id,
            contact_id=contact_id,
            deal_id=deal_id,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        _http_error(exc)
        raise
    return ActivityPageResponse(
        items=[ActivityResponse.from_model(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{activity_id}", response_model=ActivityResponse)
async def get_one(
    activity_id: UUID,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ActivityResponse:
    try:
        activity = await get_activity(session, context, activity_id)
    except Exception as exc:
        _http_error(exc)
        raise
    return ActivityResponse.from_model(activity)
