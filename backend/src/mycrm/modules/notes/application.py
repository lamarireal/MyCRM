from dataclasses import dataclass
from typing import NoReturn
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.modules.audit.application import model_snapshot, record_audit
from mycrm.modules.crm_relations import validate_crm_relations
from mycrm.modules.crm_shared import (
    EntityNotFoundError,
    RecordStatus,
    VersionConflictError,
    require_workspace_write,
)
from mycrm.modules.notes.models import Note
from mycrm.modules.workspaces.domain import WorkspaceContext


@dataclass(frozen=True, slots=True)
class NotePage:
    items: list[Note]
    total: int
    limit: int
    offset: int


async def create_note(
    session: AsyncSession,
    context: WorkspaceContext,
    *,
    body: str,
    company_id: UUID | None,
    contact_id: UUID | None,
    deal_id: UUID | None,
) -> Note:
    require_workspace_write(context.can_write)
    await validate_crm_relations(
        session,
        context,
        company_id=company_id,
        contact_id=contact_id,
        deal_id=deal_id,
    )
    note = Note(
        workspace_id=context.workspace_id,
        author_id=context.actor_id,
        body=body.strip(),
        company_id=company_id,
        contact_id=contact_id,
        deal_id=deal_id,
    )
    session.add(note)
    await session.flush()
    await session.refresh(note)
    await record_audit(
        session,
        context,
        action="created",
        entity_type="note",
        entity_id=note.id,
        before_state=None,
        after_state=model_snapshot(note),
    )
    return note


async def get_note(session: AsyncSession, context: WorkspaceContext, note_id: UUID) -> Note:
    note = await session.scalar(
        select(Note).where(
            Note.workspace_id == context.workspace_id,
            Note.id == note_id,
            Note.status == RecordStatus.ACTIVE,
        )
    )
    if note is None:
        raise EntityNotFoundError
    return note


async def list_notes(
    session: AsyncSession,
    context: WorkspaceContext,
    *,
    company_id: UUID | None,
    contact_id: UUID | None,
    deal_id: UUID | None,
    limit: int,
    offset: int,
) -> NotePage:
    filters = [Note.workspace_id == context.workspace_id, Note.status == RecordStatus.ACTIVE]
    if company_id is not None:
        filters.append(Note.company_id == company_id)
    if contact_id is not None:
        filters.append(Note.contact_id == contact_id)
    if deal_id is not None:
        filters.append(Note.deal_id == deal_id)
    items = list(
        (
            await session.scalars(
                select(Note)
                .where(*filters)
                .order_by(Note.updated_at.desc(), Note.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    total = await session.scalar(select(func.count(Note.id)).where(*filters))
    return NotePage(items, total or 0, limit, offset)


async def _update_failure(
    session: AsyncSession, context: WorkspaceContext, note_id: UUID
) -> NoReturn:
    version = await session.scalar(
        select(Note.version).where(
            Note.workspace_id == context.workspace_id,
            Note.id == note_id,
            Note.status == RecordStatus.ACTIVE,
        )
    )
    if version is None:
        raise EntityNotFoundError
    raise VersionConflictError


async def update_note(
    session: AsyncSession,
    context: WorkspaceContext,
    note_id: UUID,
    *,
    body: str,
    expected_version: int,
) -> Note:
    require_workspace_write(context.can_write)
    current = await get_note(session, context, note_id)
    before = model_snapshot(current)
    note = (
        await session.scalars(
            update(Note)
            .where(
                Note.workspace_id == context.workspace_id,
                Note.id == note_id,
                Note.status == RecordStatus.ACTIVE,
                Note.version == expected_version,
            )
            .values(body=body.strip(), version=Note.version + 1, updated_at=func.now())
            .returning(Note)
        )
    ).one_or_none()
    if note is None:
        await _update_failure(session, context, note_id)
    await record_audit(
        session,
        context,
        action="updated",
        entity_type="note",
        entity_id=note.id,
        before_state=before,
        after_state=model_snapshot(note),
    )
    return note


async def archive_note(
    session: AsyncSession, context: WorkspaceContext, note_id: UUID, *, expected_version: int
) -> Note:
    require_workspace_write(context.can_write)
    current = await get_note(session, context, note_id)
    before = model_snapshot(current)
    note = (
        await session.scalars(
            update(Note)
            .where(
                Note.workspace_id == context.workspace_id,
                Note.id == note_id,
                Note.status == RecordStatus.ACTIVE,
                Note.version == expected_version,
            )
            .values(
                status=RecordStatus.ARCHIVED,
                version=Note.version + 1,
                updated_at=func.now(),
            )
            .returning(Note)
        )
    ).one_or_none()
    if note is None:
        await _update_failure(session, context, note_id)
    await record_audit(
        session,
        context,
        action="archived",
        entity_type="note",
        entity_id=note.id,
        before_state=before,
        after_state=model_snapshot(note),
    )
    return note
