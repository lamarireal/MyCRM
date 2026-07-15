from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn, TypedDict
from uuid import UUID

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from mycrm.modules.companies.models import Company
from mycrm.modules.crm_shared import (
    EntityNotFoundError,
    RecordStatus,
    VersionConflictError,
    escape_like,
    require_workspace_write,
)
from mycrm.modules.workspaces.domain import WorkspaceContext


class CompanySort(StrEnum):
    NAME = "name"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class CompanyChanges(TypedDict, total=False):
    name: str
    website: str | None
    industry: str | None


@dataclass(frozen=True, slots=True)
class CompanyPage:
    items: list[Company]
    total: int
    limit: int
    offset: int


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


async def create_company(
    session: AsyncSession,
    context: WorkspaceContext,
    *,
    name: str,
    website: str | None,
    industry: str | None,
) -> Company:
    require_workspace_write(context.can_write)
    company = Company(
        workspace_id=context.workspace_id,
        name=name.strip(),
        website=_clean_optional(website),
        industry=_clean_optional(industry),
    )
    session.add(company)
    await session.flush()
    await session.refresh(company)
    return company


async def get_company(
    session: AsyncSession,
    context: WorkspaceContext,
    company_id: UUID,
    *,
    include_archived: bool = False,
) -> Company:
    query = select(Company).where(
        Company.workspace_id == context.workspace_id,
        Company.id == company_id,
    )
    if not include_archived:
        query = query.where(Company.status == RecordStatus.ACTIVE)
    company = await session.scalar(query)
    if company is None:
        raise EntityNotFoundError
    return company


def _company_filters(
    context: WorkspaceContext, search: str | None, include_archived: bool
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [Company.workspace_id == context.workspace_id]
    if not include_archived:
        filters.append(Company.status == RecordStatus.ACTIVE)
    if search:
        pattern = f"%{escape_like(search.strip())}%"
        filters.append(
            or_(
                Company.name.ilike(pattern, escape="\\"),
                Company.industry.ilike(pattern, escape="\\"),
            )
        )
    return filters


async def list_companies(
    session: AsyncSession,
    context: WorkspaceContext,
    *,
    search: str | None,
    include_archived: bool,
    sort: CompanySort,
    direction: SortDirection,
    limit: int,
    offset: int,
) -> CompanyPage:
    filters = _company_filters(context, search, include_archived)
    sort_column = {
        CompanySort.NAME: Company.name,
        CompanySort.CREATED_AT: Company.created_at,
        CompanySort.UPDATED_AT: Company.updated_at,
    }[sort]
    ordering = sort_column.asc() if direction == SortDirection.ASC else sort_column.desc()
    query: Select[tuple[Company]] = (
        select(Company).where(*filters).order_by(ordering, Company.id).limit(limit).offset(offset)
    )
    items = list((await session.scalars(query)).all())
    total = await session.scalar(select(func.count(Company.id)).where(*filters))
    return CompanyPage(items=items, total=total or 0, limit=limit, offset=offset)


async def _raise_update_failure(
    session: AsyncSession, context: WorkspaceContext, company_id: UUID
) -> NoReturn:
    current_version = await session.scalar(
        select(Company.version).where(
            Company.workspace_id == context.workspace_id,
            Company.id == company_id,
            Company.status == RecordStatus.ACTIVE,
        )
    )
    if current_version is None:
        raise EntityNotFoundError
    raise VersionConflictError


async def update_company(
    session: AsyncSession,
    context: WorkspaceContext,
    company_id: UUID,
    *,
    expected_version: int,
    changes: CompanyChanges,
) -> Company:
    require_workspace_write(context.can_write)
    values: dict[str, object] = {
        "version": Company.version + 1,
        "updated_at": func.now(),
    }
    if "name" in changes:
        values["name"] = changes["name"].strip()
    if "website" in changes:
        values["website"] = _clean_optional(changes["website"])
    if "industry" in changes:
        values["industry"] = _clean_optional(changes["industry"])

    statement = (
        update(Company)
        .where(
            Company.workspace_id == context.workspace_id,
            Company.id == company_id,
            Company.status == RecordStatus.ACTIVE,
            Company.version == expected_version,
        )
        .values(**values)
        .returning(Company)
    )
    company = (await session.scalars(statement)).one_or_none()
    if company is None:
        await _raise_update_failure(session, context, company_id)
    return company


async def archive_company(
    session: AsyncSession,
    context: WorkspaceContext,
    company_id: UUID,
    *,
    expected_version: int,
) -> Company:
    require_workspace_write(context.can_write)
    statement = (
        update(Company)
        .where(
            Company.workspace_id == context.workspace_id,
            Company.id == company_id,
            Company.status == RecordStatus.ACTIVE,
            Company.version == expected_version,
        )
        .values(
            status=RecordStatus.ARCHIVED,
            version=Company.version + 1,
            updated_at=func.now(),
        )
        .returning(Company)
    )
    company = (await session.scalars(statement)).one_or_none()
    if company is None:
        await _raise_update_failure(session, context, company_id)
    return company
