from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn, TypedDict
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.modules.audit.application import model_snapshot, record_audit
from mycrm.modules.crm_relations import validate_assignee, validate_crm_relations
from mycrm.modules.crm_shared import (
    EntityNotFoundError,
    VersionConflictError,
    require_workspace_write,
)
from mycrm.modules.tasks.models import Task, TaskPriority, TaskStatus
from mycrm.modules.workspaces.domain import WorkspaceContext


class TaskChanges(TypedDict, total=False):
    title: str
    description: str | None
    due_at: datetime | None
    priority: TaskPriority
    assignee_id: UUID | None
    company_id: UUID | None
    contact_id: UUID | None
    deal_id: UUID | None


@dataclass(frozen=True, slots=True)
class TaskPage:
    items: list[Task]
    total: int
    limit: int
    offset: int


async def create_task(
    session: AsyncSession,
    context: WorkspaceContext,
    *,
    title: str,
    description: str | None,
    due_at: datetime | None,
    priority: TaskPriority,
    assignee_id: UUID | None,
    company_id: UUID | None,
    contact_id: UUID | None,
    deal_id: UUID | None,
) -> Task:
    require_workspace_write(context.can_write)
    await validate_crm_relations(
        session,
        context,
        company_id=company_id,
        contact_id=contact_id,
        deal_id=deal_id,
    )
    await validate_assignee(session, context, assignee_id)
    task = Task(
        workspace_id=context.workspace_id,
        title=title.strip(),
        description=description,
        due_at=due_at,
        priority=priority,
        assignee_id=assignee_id,
        company_id=company_id,
        contact_id=contact_id,
        deal_id=deal_id,
    )
    session.add(task)
    await session.flush()
    await session.refresh(task)
    await record_audit(
        session,
        context,
        action="created",
        entity_type="task",
        entity_id=task.id,
        before_state=None,
        after_state=model_snapshot(task),
    )
    return task


async def get_task(session: AsyncSession, context: WorkspaceContext, task_id: UUID) -> Task:
    task = await session.scalar(
        select(Task).where(
            Task.workspace_id == context.workspace_id,
            Task.id == task_id,
            Task.status != TaskStatus.ARCHIVED,
        )
    )
    if task is None:
        raise EntityNotFoundError
    return task


async def list_tasks(
    session: AsyncSession,
    context: WorkspaceContext,
    *,
    status: TaskStatus | None,
    assignee_id: UUID | None,
    deal_id: UUID | None,
    limit: int,
    offset: int,
) -> TaskPage:
    filters = [Task.workspace_id == context.workspace_id, Task.status != TaskStatus.ARCHIVED]
    if status is not None:
        filters.append(Task.status == status)
    if assignee_id is not None:
        filters.append(Task.assignee_id == assignee_id)
    if deal_id is not None:
        filters.append(Task.deal_id == deal_id)
    items = list(
        (
            await session.scalars(
                select(Task)
                .where(*filters)
                .order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc(), Task.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    total = await session.scalar(select(func.count(Task.id)).where(*filters))
    return TaskPage(items, total or 0, limit, offset)


async def _update_failure(
    session: AsyncSession, context: WorkspaceContext, task_id: UUID
) -> NoReturn:
    version = await session.scalar(
        select(Task.version).where(
            Task.workspace_id == context.workspace_id,
            Task.id == task_id,
            Task.status != TaskStatus.ARCHIVED,
        )
    )
    if version is None:
        raise EntityNotFoundError
    raise VersionConflictError


async def update_task(
    session: AsyncSession,
    context: WorkspaceContext,
    task_id: UUID,
    *,
    expected_version: int,
    changes: TaskChanges,
) -> Task:
    require_workspace_write(context.can_write)
    current = await get_task(session, context, task_id)
    before = model_snapshot(current)
    company_id = changes.get("company_id", current.company_id)
    contact_id = changes.get("contact_id", current.contact_id)
    deal_id = changes.get("deal_id", current.deal_id)
    if {"company_id", "contact_id", "deal_id"} & changes.keys():
        await validate_crm_relations(
            session,
            context,
            company_id=company_id,
            contact_id=contact_id,
            deal_id=deal_id,
        )
    if "assignee_id" in changes:
        await validate_assignee(session, context, changes["assignee_id"])
    values: dict[str, object] = {"version": Task.version + 1, "updated_at": func.now()}
    values.update(changes)
    if "title" in changes:
        values["title"] = changes["title"].strip()
    task = (
        await session.scalars(
            update(Task)
            .where(
                Task.workspace_id == context.workspace_id,
                Task.id == task_id,
                Task.status != TaskStatus.ARCHIVED,
                Task.version == expected_version,
            )
            .values(**values)
            .returning(Task)
        )
    ).one_or_none()
    if task is None:
        await _update_failure(session, context, task_id)
    await record_audit(
        session,
        context,
        action="updated",
        entity_type="task",
        entity_id=task.id,
        before_state=before,
        after_state=model_snapshot(task),
    )
    return task


async def change_task_status(
    session: AsyncSession,
    context: WorkspaceContext,
    task_id: UUID,
    *,
    target_status: TaskStatus,
    expected_version: int,
) -> Task:
    require_workspace_write(context.can_write)
    if target_status == TaskStatus.ARCHIVED:
        raise ValueError("Archive uses the dedicated archive command")
    current = await get_task(session, context, task_id)
    before = model_snapshot(current)
    completed_at = func.now() if target_status == TaskStatus.DONE else None
    task = (
        await session.scalars(
            update(Task)
            .where(
                Task.workspace_id == context.workspace_id,
                Task.id == task_id,
                Task.status != TaskStatus.ARCHIVED,
                Task.version == expected_version,
            )
            .values(
                status=target_status,
                completed_at=completed_at,
                version=Task.version + 1,
                updated_at=func.now(),
            )
            .returning(Task)
        )
    ).one_or_none()
    if task is None:
        await _update_failure(session, context, task_id)
    await record_audit(
        session,
        context,
        action="status_changed",
        entity_type="task",
        entity_id=task.id,
        before_state=before,
        after_state=model_snapshot(task),
    )
    return task


async def archive_task(
    session: AsyncSession, context: WorkspaceContext, task_id: UUID, *, expected_version: int
) -> Task:
    require_workspace_write(context.can_write)
    current = await get_task(session, context, task_id)
    before = model_snapshot(current)
    task = (
        await session.scalars(
            update(Task)
            .where(
                Task.workspace_id == context.workspace_id,
                Task.id == task_id,
                Task.status != TaskStatus.ARCHIVED,
                Task.version == expected_version,
            )
            .values(
                status=TaskStatus.ARCHIVED,
                version=Task.version + 1,
                updated_at=func.now(),
            )
            .returning(Task)
        )
    ).one_or_none()
    if task is None:
        await _update_failure(session, context, task_id)
    await record_audit(
        session,
        context,
        action="archived",
        entity_type="task",
        entity_id=task.id,
        before_state=before,
        after_state=model_snapshot(task),
    )
    return task
