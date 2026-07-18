from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import NoReturn, TypedDict
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from mycrm.modules.audit.application import model_snapshot, record_audit
from mycrm.modules.companies.models import Company
from mycrm.modules.contacts.models import Contact
from mycrm.modules.crm_shared import (
    EntityNotFoundError,
    RecordStatus,
    RelatedEntityMismatchError,
    RelatedEntityNotFoundError,
    VersionConflictError,
    escape_like,
    require_workspace_write,
)
from mycrm.modules.deals.models import Deal, DealStatus
from mycrm.modules.pipelines.models import Pipeline, PipelineStage, StageOutcome
from mycrm.modules.workspaces.domain import WorkspaceContext


class DealChanges(TypedDict, total=False):
    title: str
    company_id: UUID | None
    contact_id: UUID | None
    amount: Decimal | None
    currency: str
    probability: int
    expected_close_date: date | None


@dataclass(frozen=True, slots=True)
class DealPage:
    items: list[Deal]
    total: int
    limit: int
    offset: int


def _deal_status(outcome: StageOutcome) -> DealStatus:
    return {
        StageOutcome.OPEN: DealStatus.OPEN,
        StageOutcome.WON: DealStatus.WON,
        StageOutcome.LOST: DealStatus.LOST,
    }[outcome]


async def _stage(
    session: AsyncSession, context: WorkspaceContext, pipeline_id: UUID, stage_id: UUID
) -> PipelineStage:
    stage = await session.scalar(
        select(PipelineStage)
        .join(
            Pipeline,
            (Pipeline.workspace_id == PipelineStage.workspace_id)
            & (Pipeline.id == PipelineStage.pipeline_id),
        )
        .where(
            PipelineStage.workspace_id == context.workspace_id,
            PipelineStage.pipeline_id == pipeline_id,
            PipelineStage.id == stage_id,
            PipelineStage.status == RecordStatus.ACTIVE,
            Pipeline.status == RecordStatus.ACTIVE,
        )
    )
    if stage is None:
        raise RelatedEntityNotFoundError
    return stage


async def _relations(
    session: AsyncSession,
    context: WorkspaceContext,
    company_id: UUID | None,
    contact_id: UUID | None,
) -> None:
    company: Company | None = None
    if company_id is not None:
        company = await session.scalar(
            select(Company).where(
                Company.workspace_id == context.workspace_id,
                Company.id == company_id,
                Company.status == RecordStatus.ACTIVE,
            )
        )
        if company is None:
            raise RelatedEntityNotFoundError
    if contact_id is not None:
        contact = await session.scalar(
            select(Contact).where(
                Contact.workspace_id == context.workspace_id,
                Contact.id == contact_id,
                Contact.status == RecordStatus.ACTIVE,
            )
        )
        if contact is None:
            raise RelatedEntityNotFoundError
        if company is not None and contact.company_id not in {None, company.id}:
            raise RelatedEntityMismatchError


async def create_deal(
    session: AsyncSession,
    context: WorkspaceContext,
    *,
    pipeline_id: UUID,
    stage_id: UUID,
    company_id: UUID | None,
    contact_id: UUID | None,
    title: str,
    amount: Decimal | None,
    currency: str,
    probability: int | None,
    expected_close_date: date | None,
) -> Deal:
    require_workspace_write(context.can_write)
    stage = await _stage(session, context, pipeline_id, stage_id)
    await _relations(session, context, company_id, contact_id)
    deal = Deal(
        workspace_id=context.workspace_id,
        pipeline_id=pipeline_id,
        stage_id=stage_id,
        company_id=company_id,
        contact_id=contact_id,
        title=title.strip(),
        amount=amount,
        currency=currency.upper(),
        probability=stage.probability if probability is None else probability,
        expected_close_date=expected_close_date,
        status=_deal_status(stage.outcome),
    )
    session.add(deal)
    await session.flush()
    await session.refresh(deal)
    await record_audit(
        session,
        context,
        action="created",
        entity_type="deal",
        entity_id=deal.id,
        before_state=None,
        after_state=model_snapshot(deal),
    )
    return deal


async def get_deal(session: AsyncSession, context: WorkspaceContext, deal_id: UUID) -> Deal:
    deal = await session.scalar(
        select(Deal).where(
            Deal.workspace_id == context.workspace_id,
            Deal.id == deal_id,
            Deal.status != DealStatus.ARCHIVED,
        )
    )
    if deal is None:
        raise EntityNotFoundError
    return deal


async def list_deals(
    session: AsyncSession,
    context: WorkspaceContext,
    *,
    search: str | None,
    pipeline_id: UUID | None,
    stage_id: UUID | None,
    status: DealStatus | None,
    limit: int,
    offset: int,
) -> DealPage:
    filters: list[ColumnElement[bool]] = [
        Deal.workspace_id == context.workspace_id,
        Deal.status != DealStatus.ARCHIVED,
    ]
    if pipeline_id is not None:
        filters.append(Deal.pipeline_id == pipeline_id)
    if stage_id is not None:
        filters.append(Deal.stage_id == stage_id)
    if status is not None:
        filters.append(Deal.status == status)
    if search:
        filters.append(Deal.title.ilike(f"%{escape_like(search.strip())}%", escape="\\"))
    query: Select[tuple[Deal]] = (
        select(Deal)
        .where(*filters)
        .order_by(Deal.updated_at.desc(), Deal.id)
        .limit(limit)
        .offset(offset)
    )
    items = list((await session.scalars(query)).all())
    total = await session.scalar(select(func.count(Deal.id)).where(*filters))
    return DealPage(items=items, total=total or 0, limit=limit, offset=offset)


async def _update_failure(
    session: AsyncSession, context: WorkspaceContext, deal_id: UUID
) -> NoReturn:
    version = await session.scalar(
        select(Deal.version).where(
            Deal.workspace_id == context.workspace_id,
            Deal.id == deal_id,
            Deal.status != DealStatus.ARCHIVED,
        )
    )
    if version is None:
        raise EntityNotFoundError
    raise VersionConflictError


async def update_deal(
    session: AsyncSession,
    context: WorkspaceContext,
    deal_id: UUID,
    *,
    expected_version: int,
    changes: DealChanges,
) -> Deal:
    require_workspace_write(context.can_write)
    current = await get_deal(session, context, deal_id)
    before = model_snapshot(current)
    company_id = changes.get("company_id", current.company_id)
    contact_id = changes.get("contact_id", current.contact_id)
    if "company_id" in changes or "contact_id" in changes:
        await _relations(session, context, company_id, contact_id)
    values: dict[str, object] = {"version": Deal.version + 1, "updated_at": func.now()}
    values.update(changes)
    if "title" in changes:
        values["title"] = changes["title"].strip()
    if "currency" in changes:
        values["currency"] = changes["currency"].upper()
    statement = (
        update(Deal)
        .where(
            Deal.workspace_id == context.workspace_id,
            Deal.id == deal_id,
            Deal.status != DealStatus.ARCHIVED,
            Deal.version == expected_version,
        )
        .values(**values)
        .returning(Deal)
    )
    deal = (await session.scalars(statement)).one_or_none()
    if deal is None:
        await _update_failure(session, context, deal_id)
    await record_audit(
        session,
        context,
        action="updated",
        entity_type="deal",
        entity_id=deal.id,
        before_state=before,
        after_state=model_snapshot(deal),
    )
    return deal


async def move_deal_stage(
    session: AsyncSession,
    context: WorkspaceContext,
    deal_id: UUID,
    *,
    stage_id: UUID,
    expected_version: int,
) -> Deal:
    require_workspace_write(context.can_write)
    current = await get_deal(session, context, deal_id)
    before = model_snapshot(current)
    target = await _stage(session, context, current.pipeline_id, stage_id)
    statement = (
        update(Deal)
        .where(
            Deal.workspace_id == context.workspace_id,
            Deal.id == deal_id,
            Deal.status != DealStatus.ARCHIVED,
            Deal.version == expected_version,
        )
        .values(
            stage_id=target.id,
            probability=target.probability,
            status=_deal_status(target.outcome),
            version=Deal.version + 1,
            updated_at=func.now(),
        )
        .returning(Deal)
    )
    deal = (await session.scalars(statement)).one_or_none()
    if deal is None:
        await _update_failure(session, context, deal_id)
    await record_audit(
        session,
        context,
        action="stage_changed",
        entity_type="deal",
        entity_id=deal.id,
        before_state=before,
        after_state=model_snapshot(deal),
    )
    return deal


async def archive_deal(
    session: AsyncSession, context: WorkspaceContext, deal_id: UUID, *, expected_version: int
) -> Deal:
    require_workspace_write(context.can_write)
    current = await get_deal(session, context, deal_id)
    before = model_snapshot(current)
    statement = (
        update(Deal)
        .where(
            Deal.workspace_id == context.workspace_id,
            Deal.id == deal_id,
            Deal.status != DealStatus.ARCHIVED,
            Deal.version == expected_version,
        )
        .values(status=DealStatus.ARCHIVED, version=Deal.version + 1, updated_at=func.now())
        .returning(Deal)
    )
    deal = (await session.scalars(statement)).one_or_none()
    if deal is None:
        await _update_failure(session, context, deal_id)
    await record_audit(
        session,
        context,
        action="archived",
        entity_type="deal",
        entity_id=deal.id,
        before_state=before,
        after_state=model_snapshot(deal),
    )
    return deal
