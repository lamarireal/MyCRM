from datetime import datetime
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.database import get_session
from mycrm.modules.crm_shared import (
    EntityNotFoundError,
    RelatedEntityNotFoundError,
    VersionConflictError,
    WorkspaceWriteForbiddenError,
)
from mycrm.modules.tasks.application import (
    TaskChanges,
    archive_task,
    change_task_status,
    create_task,
    get_task,
    list_tasks,
    update_task,
)
from mycrm.modules.tasks.models import Task, TaskPriority, TaskStatus
from mycrm.modules.workspaces.dependencies import CurrentWorkspace

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    due_at: datetime | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_id: UUID | None = None
    company_id: UUID | None = None
    contact_id: UUID | None = None
    deal_id: UUID | None = None


class TaskUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    due_at: datetime | None = None
    priority: TaskPriority | None = None
    assignee_id: UUID | None = None
    company_id: UUID | None = None
    contact_id: UUID | None = None
    deal_id: UUID | None = None

    @model_validator(mode="after")
    def require_change(self) -> "TaskUpdateRequest":
        changed = self.model_fields_set - {"expected_version"}
        if not changed:
            raise ValueError("At least one field must be changed")
        for required in ("title", "priority"):
            if required in changed and getattr(self, required) is None:
                raise ValueError(f"{required} cannot be null")
        return self


class TaskStatusRequest(BaseModel):
    status: TaskStatus
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def reject_archive(self) -> "TaskStatusRequest":
        if self.status == TaskStatus.ARCHIVED:
            raise ValueError("Use DELETE to archive a task")
        return self


class TaskResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    company_id: UUID | None
    contact_id: UUID | None
    deal_id: UUID | None
    assignee_id: UUID | None
    title: str
    description: str | None
    due_at: datetime | None
    priority: TaskPriority
    status: TaskStatus
    completed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, task: Task) -> "TaskResponse":
        return cls.model_validate(task, from_attributes=True)


class TaskPageResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    limit: int
    offset: int


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


def _http_error(exc: Exception) -> None:
    if isinstance(exc, EntityNotFoundError):
        raise HTTPException(status_code=404, detail="Task not found") from exc
    if isinstance(exc, RelatedEntityNotFoundError):
        raise HTTPException(
            status_code=404, detail="Related CRM record or assignee not found"
        ) from exc
    if isinstance(exc, VersionConflictError):
        raise HTTPException(status_code=409, detail="Task version conflict") from exc
    if isinstance(exc, WorkspaceWriteForbiddenError):
        raise HTTPException(status_code=403, detail="Workspace is read-only") from exc
    raise exc


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create(
    payload: TaskCreateRequest,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TaskResponse:
    try:
        task = await create_task(session, context, **payload.model_dump())
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, task.version)
    return TaskResponse.from_model(task)


@router.get("", response_model=TaskPageResponse)
async def list_all(
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
    assignee_id: UUID | None = None,
    deal_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TaskPageResponse:
    page = await list_tasks(
        session,
        context,
        status=task_status,
        assignee_id=assignee_id,
        deal_id=deal_id,
        limit=limit,
        offset=offset,
    )
    return TaskPageResponse(
        items=[TaskResponse.from_model(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_one(
    task_id: UUID,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TaskResponse:
    try:
        task = await get_task(session, context, task_id)
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, task.version)
    return TaskResponse.from_model(task)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_one(
    task_id: UUID,
    payload: TaskUpdateRequest,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TaskResponse:
    changes: dict[str, Any] = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    try:
        task = await update_task(
            session,
            context,
            task_id,
            expected_version=payload.expected_version,
            changes=cast(TaskChanges, changes),
        )
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, task.version)
    return TaskResponse.from_model(task)


@router.post("/{task_id}/change-status", response_model=TaskResponse)
async def change_status(
    task_id: UUID,
    payload: TaskStatusRequest,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TaskResponse:
    try:
        task = await change_task_status(
            session,
            context,
            task_id,
            target_status=payload.status,
            expected_version=payload.expected_version,
        )
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, task.version)
    return TaskResponse.from_model(task)


@router.delete("/{task_id}", response_model=TaskResponse)
async def archive_one(
    task_id: UUID,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
    expected_version: Annotated[int, Query(ge=1)],
) -> TaskResponse:
    try:
        task = await archive_task(session, context, task_id, expected_version=expected_version)
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, task.version)
    return TaskResponse.from_model(task)
