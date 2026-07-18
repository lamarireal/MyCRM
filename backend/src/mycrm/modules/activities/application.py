from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.modules.activities.models import Activity, ActivitySource, ActivityType
from mycrm.modules.audit.application import model_snapshot, record_audit
from mycrm.modules.audit.models import AuditSource
from mycrm.modules.crm_relations import validate_crm_relations
from mycrm.modules.crm_shared import EntityNotFoundError, require_workspace_write
from mycrm.modules.workspaces.domain import WorkspaceContext


@dataclass(frozen=True, slots=True)
class ActivityPage:
    items: list[Activity]
    next_cursor: UUID | None


async def create_activity(
    session: AsyncSession,
    context: WorkspaceContext,
    *,
    activity_type: ActivityType,
    summary: str,
    details: str | None,
    occurred_at: datetime,
    company_id: UUID | None,
    contact_id: UUID | None,
    deal_id: UUID | None,
    source: ActivitySource = ActivitySource.HUMAN,
) -> Activity:
    require_workspace_write(context.can_write)
    await validate_crm_relations(
        session,
        context,
        company_id=company_id,
        contact_id=contact_id,
        deal_id=deal_id,
    )
    activity = Activity(
        workspace_id=context.workspace_id,
        created_by_id=context.actor_id,
        activity_type=activity_type,
        source=source,
        summary=summary.strip(),
        details=details,
        occurred_at=occurred_at,
        company_id=company_id,
        contact_id=contact_id,
        deal_id=deal_id,
    )
    session.add(activity)
    await session.flush()
    await session.refresh(activity)
    await record_audit(
        session,
        context,
        action="created",
        entity_type="activity",
        entity_id=activity.id,
        before_state=None,
        after_state=model_snapshot(activity),
        source=AuditSource(source.value),
    )
    return activity


async def get_activity(
    session: AsyncSession, context: WorkspaceContext, activity_id: UUID
) -> Activity:
    activity = await session.scalar(
        select(Activity).where(
            Activity.workspace_id == context.workspace_id, Activity.id == activity_id
        )
    )
    if activity is None:
        raise EntityNotFoundError
    return activity


async def list_activities(
    session: AsyncSession,
    context: WorkspaceContext,
    *,
    company_id: UUID | None,
    contact_id: UUID | None,
    deal_id: UUID | None,
    cursor: UUID | None,
    limit: int,
) -> ActivityPage:
    filters = [Activity.workspace_id == context.workspace_id]
    if company_id is not None:
        filters.append(Activity.company_id == company_id)
    if contact_id is not None:
        filters.append(Activity.contact_id == contact_id)
    if deal_id is not None:
        filters.append(Activity.deal_id == deal_id)
    if cursor is not None:
        boundary = await get_activity(session, context, cursor)
        filters.append(
            or_(
                Activity.occurred_at < boundary.occurred_at,
                and_(Activity.occurred_at == boundary.occurred_at, Activity.id > boundary.id),
            )
        )
    rows = list(
        (
            await session.scalars(
                select(Activity)
                .where(*filters)
                .order_by(Activity.occurred_at.desc(), Activity.id)
                .limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    items = rows[:limit]
    return ActivityPage(items, items[-1].id if has_more else None)
