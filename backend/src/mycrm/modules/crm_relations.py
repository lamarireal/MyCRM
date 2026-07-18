from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.modules.companies.models import Company
from mycrm.modules.contacts.models import Contact
from mycrm.modules.crm_shared import RecordStatus, RelatedEntityNotFoundError
from mycrm.modules.deals.models import Deal, DealStatus
from mycrm.modules.workspaces.domain import MembershipStatus, WorkspaceContext
from mycrm.modules.workspaces.models import WorkspaceMembership


async def validate_crm_relations(
    session: AsyncSession,
    context: WorkspaceContext,
    *,
    company_id: UUID | None,
    contact_id: UUID | None,
    deal_id: UUID | None,
) -> None:
    checks = (
        (
            company_id,
            select(Company.id).where(
                Company.workspace_id == context.workspace_id,
                Company.id == company_id,
                Company.status == RecordStatus.ACTIVE,
            ),
        ),
        (
            contact_id,
            select(Contact.id).where(
                Contact.workspace_id == context.workspace_id,
                Contact.id == contact_id,
                Contact.status == RecordStatus.ACTIVE,
            ),
        ),
        (
            deal_id,
            select(Deal.id).where(
                Deal.workspace_id == context.workspace_id,
                Deal.id == deal_id,
                Deal.status != DealStatus.ARCHIVED,
            ),
        ),
    )
    for record_id, statement in checks:
        if record_id is not None and await session.scalar(statement) is None:
            raise RelatedEntityNotFoundError


async def validate_assignee(
    session: AsyncSession, context: WorkspaceContext, assignee_id: UUID | None
) -> None:
    if assignee_id is None:
        return
    membership_id = await session.scalar(
        select(WorkspaceMembership.id).where(
            WorkspaceMembership.workspace_id == context.workspace_id,
            WorkspaceMembership.user_id == assignee_id,
            WorkspaceMembership.status == MembershipStatus.ACTIVE,
        )
    )
    if membership_id is None:
        raise RelatedEntityNotFoundError
