from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, inspect, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.state import InstanceState

from mycrm.modules.audit.models import AuditRecord, AuditSource
from mycrm.modules.crm_shared import EntityNotFoundError
from mycrm.modules.workspaces.domain import WorkspaceContext


@dataclass(frozen=True, slots=True)
class AuditPage:
    items: list[AuditRecord]
    next_cursor: UUID | None


def _json_value(value: object) -> Any:
    if isinstance(value, UUID | datetime | date | Decimal | Enum):
        return str(value.value if isinstance(value, Enum) else value)
    return value


def model_snapshot(model: object) -> dict[str, Any]:
    mapper = cast(InstanceState[Any], inspect(model)).mapper
    return {
        attribute.key: _json_value(getattr(model, attribute.key))
        for attribute in mapper.column_attrs
    }


async def record_audit(
    session: AsyncSession,
    context: WorkspaceContext,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID,
    before_state: dict[str, Any] | None,
    after_state: dict[str, Any] | None,
    source: AuditSource = AuditSource.HUMAN,
) -> AuditRecord:
    record = AuditRecord(
        workspace_id=context.workspace_id,
        actor_id=context.actor_id,
        source=source,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
    )
    session.add(record)
    await session.flush()
    return record


async def get_audit_record(
    session: AsyncSession, context: WorkspaceContext, record_id: UUID
) -> AuditRecord:
    record = await session.scalar(
        select(AuditRecord).where(
            AuditRecord.workspace_id == context.workspace_id,
            AuditRecord.id == record_id,
        )
    )
    if record is None:
        raise EntityNotFoundError
    return record


async def list_audit_records(
    session: AsyncSession,
    context: WorkspaceContext,
    *,
    entity_type: str | None,
    entity_id: UUID | None,
    cursor: UUID | None,
    limit: int,
) -> AuditPage:
    filters = [AuditRecord.workspace_id == context.workspace_id]
    if entity_type is not None:
        filters.append(AuditRecord.entity_type == entity_type)
    if entity_id is not None:
        filters.append(AuditRecord.entity_id == entity_id)
    if cursor is not None:
        boundary = await get_audit_record(session, context, cursor)
        filters.append(
            or_(
                AuditRecord.created_at < boundary.created_at,
                and_(
                    AuditRecord.created_at == boundary.created_at,
                    AuditRecord.id > boundary.id,
                ),
            )
        )
    rows = list(
        (
            await session.scalars(
                select(AuditRecord)
                .where(*filters)
                .order_by(AuditRecord.created_at.desc(), AuditRecord.id)
                .limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    items = rows[:limit]
    return AuditPage(items=items, next_cursor=items[-1].id if has_more else None)
