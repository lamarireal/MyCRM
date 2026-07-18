from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.database import get_session
from mycrm.modules.audit.application import get_audit_record, list_audit_records
from mycrm.modules.audit.models import AuditRecord, AuditSource
from mycrm.modules.crm_shared import EntityNotFoundError
from mycrm.modules.workspaces.dependencies import CurrentWorkspace

router = APIRouter(prefix="/audit-records", tags=["audit"])


class AuditRecordResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    actor_id: UUID | None
    source: AuditSource
    action: str
    entity_type: str
    entity_id: UUID
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    created_at: datetime

    @classmethod
    def from_model(cls, record: AuditRecord) -> "AuditRecordResponse":
        return cls.model_validate(record, from_attributes=True)


class AuditPageResponse(BaseModel):
    items: list[AuditRecordResponse]
    next_cursor: UUID | None


@router.get("", response_model=AuditPageResponse)
async def list_all(
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
    entity_type: Annotated[str | None, Query(max_length=60)] = None,
    entity_id: UUID | None = None,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AuditPageResponse:
    try:
        page = await list_audit_records(
            session,
            context,
            entity_type=entity_type,
            entity_id=entity_id,
            cursor=cursor,
            limit=limit,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Audit cursor not found") from exc
    return AuditPageResponse(
        items=[AuditRecordResponse.from_model(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{record_id}", response_model=AuditRecordResponse)
async def get_one(
    record_id: UUID,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuditRecordResponse:
    try:
        record = await get_audit_record(session, context, record_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Audit record not found") from exc
    return AuditRecordResponse.from_model(record)
