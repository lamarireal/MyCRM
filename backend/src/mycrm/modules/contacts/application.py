from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn, TypedDict
from uuid import UUID

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from mycrm.modules.companies.models import Company
from mycrm.modules.contacts.models import Contact
from mycrm.modules.crm_shared import (
    EntityNotFoundError,
    RecordStatus,
    RelatedEntityNotFoundError,
    VersionConflictError,
    escape_like,
    require_workspace_write,
)
from mycrm.modules.workspaces.domain import WorkspaceContext


class ContactSort(StrEnum):
    NAME = "name"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class ContactChanges(TypedDict, total=False):
    company_id: UUID | None
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    job_title: str | None


@dataclass(frozen=True, slots=True)
class ContactPage:
    items: list[Contact]
    total: int
    limit: int
    offset: int


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


async def _require_company(
    session: AsyncSession, context: WorkspaceContext, company_id: UUID | None
) -> None:
    if company_id is None:
        return
    exists = await session.scalar(
        select(Company.id).where(
            Company.workspace_id == context.workspace_id,
            Company.id == company_id,
            Company.status == RecordStatus.ACTIVE,
        )
    )
    if exists is None:
        raise RelatedEntityNotFoundError


async def create_contact(
    session: AsyncSession,
    context: WorkspaceContext,
    *,
    company_id: UUID | None,
    first_name: str,
    last_name: str,
    email: str | None,
    phone: str | None,
    job_title: str | None,
) -> Contact:
    require_workspace_write(context.can_write)
    await _require_company(session, context, company_id)
    contact = Contact(
        workspace_id=context.workspace_id,
        company_id=company_id,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        email=_clean_optional(email.lower() if email else email),
        phone=_clean_optional(phone),
        job_title=_clean_optional(job_title),
    )
    session.add(contact)
    await session.flush()
    await session.refresh(contact)
    return contact


async def get_contact(
    session: AsyncSession,
    context: WorkspaceContext,
    contact_id: UUID,
    *,
    include_archived: bool = False,
) -> Contact:
    query = select(Contact).where(
        Contact.workspace_id == context.workspace_id,
        Contact.id == contact_id,
    )
    if not include_archived:
        query = query.where(Contact.status == RecordStatus.ACTIVE)
    contact = await session.scalar(query)
    if contact is None:
        raise EntityNotFoundError
    return contact


def _contact_filters(
    context: WorkspaceContext,
    search: str | None,
    company_id: UUID | None,
    include_archived: bool,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [Contact.workspace_id == context.workspace_id]
    if not include_archived:
        filters.append(Contact.status == RecordStatus.ACTIVE)
    if company_id is not None:
        filters.append(Contact.company_id == company_id)
    if search:
        pattern = f"%{escape_like(search.strip())}%"
        filters.append(
            or_(
                Contact.first_name.ilike(pattern, escape="\\"),
                Contact.last_name.ilike(pattern, escape="\\"),
                Contact.email.ilike(pattern, escape="\\"),
                Contact.phone.ilike(pattern, escape="\\"),
            )
        )
    return filters


async def list_contacts(
    session: AsyncSession,
    context: WorkspaceContext,
    *,
    search: str | None,
    company_id: UUID | None,
    include_archived: bool,
    sort: ContactSort,
    direction: SortDirection,
    limit: int,
    offset: int,
) -> ContactPage:
    filters = _contact_filters(context, search, company_id, include_archived)
    sort_columns = {
        ContactSort.NAME: (Contact.last_name, Contact.first_name),
        ContactSort.CREATED_AT: (Contact.created_at,),
        ContactSort.UPDATED_AT: (Contact.updated_at,),
    }[sort]
    ordering = [
        column.asc() if direction == SortDirection.ASC else column.desc() for column in sort_columns
    ]
    query: Select[tuple[Contact]] = (
        select(Contact).where(*filters).order_by(*ordering, Contact.id).limit(limit).offset(offset)
    )
    items = list((await session.scalars(query)).all())
    total = await session.scalar(select(func.count(Contact.id)).where(*filters))
    return ContactPage(items=items, total=total or 0, limit=limit, offset=offset)


async def _raise_update_failure(
    session: AsyncSession, context: WorkspaceContext, contact_id: UUID
) -> NoReturn:
    current_version = await session.scalar(
        select(Contact.version).where(
            Contact.workspace_id == context.workspace_id,
            Contact.id == contact_id,
            Contact.status == RecordStatus.ACTIVE,
        )
    )
    if current_version is None:
        raise EntityNotFoundError
    raise VersionConflictError


async def update_contact(
    session: AsyncSession,
    context: WorkspaceContext,
    contact_id: UUID,
    *,
    expected_version: int,
    changes: ContactChanges,
) -> Contact:
    require_workspace_write(context.can_write)
    if "company_id" in changes:
        await _require_company(session, context, changes["company_id"])

    values: dict[str, object] = {
        "version": Contact.version + 1,
        "updated_at": func.now(),
    }
    if "first_name" in changes:
        values["first_name"] = changes["first_name"].strip()
    if "last_name" in changes:
        values["last_name"] = changes["last_name"].strip()
    if "email" in changes:
        email = changes["email"]
        values["email"] = _clean_optional(email.lower() if email else email)
    if "phone" in changes:
        values["phone"] = _clean_optional(changes["phone"])
    if "job_title" in changes:
        values["job_title"] = _clean_optional(changes["job_title"])
    if "company_id" in changes:
        values["company_id"] = changes["company_id"]

    statement = (
        update(Contact)
        .where(
            Contact.workspace_id == context.workspace_id,
            Contact.id == contact_id,
            Contact.status == RecordStatus.ACTIVE,
            Contact.version == expected_version,
        )
        .values(**values)
        .returning(Contact)
    )
    contact = (await session.scalars(statement)).one_or_none()
    if contact is None:
        await _raise_update_failure(session, context, contact_id)
    return contact


async def archive_contact(
    session: AsyncSession,
    context: WorkspaceContext,
    contact_id: UUID,
    *,
    expected_version: int,
) -> Contact:
    require_workspace_write(context.can_write)
    statement = (
        update(Contact)
        .where(
            Contact.workspace_id == context.workspace_id,
            Contact.id == contact_id,
            Contact.status == RecordStatus.ACTIVE,
            Contact.version == expected_version,
        )
        .values(
            status=RecordStatus.ARCHIVED,
            version=Contact.version + 1,
            updated_at=func.now(),
        )
        .returning(Contact)
    )
    contact = (await session.scalars(statement)).one_or_none()
    if contact is None:
        await _raise_update_failure(session, context, contact_id)
    return contact
