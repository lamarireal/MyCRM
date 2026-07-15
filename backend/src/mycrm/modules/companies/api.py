from datetime import datetime
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import AnyHttpUrl, BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.database import get_session
from mycrm.modules.companies.application import (
    CompanyChanges,
    CompanySort,
    SortDirection,
    archive_company,
    create_company,
    get_company,
    list_companies,
    update_company,
)
from mycrm.modules.companies.models import Company
from mycrm.modules.crm_shared import (
    EntityNotFoundError,
    VersionConflictError,
    WorkspaceWriteForbiddenError,
)
from mycrm.modules.workspaces.dependencies import CurrentWorkspace

router = APIRouter(prefix="/companies", tags=["companies"])


class CompanyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    website: AnyHttpUrl | None = None
    industry: str | None = Field(default=None, max_length=120)


class CompanyUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    website: AnyHttpUrl | None = None
    industry: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def require_change(self) -> "CompanyUpdateRequest":
        changed = self.model_fields_set - {"expected_version"}
        if not changed:
            raise ValueError("At least one field must be changed")
        if "name" in changed and self.name is None:
            raise ValueError("Company name cannot be null")
        return self


class CompanyResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    website: str | None
    industry: str | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, company: Company) -> "CompanyResponse":
        return cls(
            id=company.id,
            workspace_id=company.workspace_id,
            name=company.name,
            website=company.website,
            industry=company.industry,
            status=company.status.value,
            version=company.version,
            created_at=company.created_at,
            updated_at=company.updated_at,
        )


class CompanyPageResponse(BaseModel):
    items: list[CompanyResponse]
    total: int
    limit: int
    offset: int


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, EntityNotFoundError):
        raise HTTPException(status_code=404, detail="Company not found") from exc
    if isinstance(exc, VersionConflictError):
        raise HTTPException(status_code=409, detail="Company version conflict") from exc
    if isinstance(exc, WorkspaceWriteForbiddenError):
        raise HTTPException(status_code=403, detail="Workspace is read-only") from exc
    raise exc


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create(
    payload: CompanyCreateRequest,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CompanyResponse:
    try:
        company = await create_company(
            session,
            context,
            name=payload.name,
            website=str(payload.website) if payload.website else None,
            industry=payload.industry,
        )
    except Exception as exc:
        _raise_http_error(exc)
        raise
    _etag(response, company.version)
    return CompanyResponse.from_model(company)


@router.get("", response_model=CompanyPageResponse)
async def list_all(
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
    search: Annotated[str | None, Query(max_length=200)] = None,
    include_archived: bool = False,
    sort: CompanySort = CompanySort.NAME,
    direction: SortDirection = SortDirection.ASC,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CompanyPageResponse:
    page = await list_companies(
        session,
        context,
        search=search,
        include_archived=include_archived,
        sort=sort,
        direction=direction,
        limit=limit,
        offset=offset,
    )
    return CompanyPageResponse(
        items=[CompanyResponse.from_model(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_one(
    company_id: UUID,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
    include_archived: bool = False,
) -> CompanyResponse:
    try:
        company = await get_company(session, context, company_id, include_archived=include_archived)
    except Exception as exc:
        _raise_http_error(exc)
        raise
    _etag(response, company.version)
    return CompanyResponse.from_model(company)


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_one(
    company_id: UUID,
    payload: CompanyUpdateRequest,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CompanyResponse:
    raw_changes: dict[str, Any] = payload.model_dump(
        exclude_unset=True, exclude={"expected_version"}
    )
    if "website" in raw_changes and raw_changes["website"] is not None:
        raw_changes["website"] = str(raw_changes["website"])
    try:
        company = await update_company(
            session,
            context,
            company_id,
            expected_version=payload.expected_version,
            changes=cast(CompanyChanges, raw_changes),
        )
    except Exception as exc:
        _raise_http_error(exc)
        raise
    _etag(response, company.version)
    return CompanyResponse.from_model(company)


@router.delete("/{company_id}", response_model=CompanyResponse)
async def archive_one(
    company_id: UUID,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
    expected_version: Annotated[int, Query(ge=1)],
) -> CompanyResponse:
    try:
        company = await archive_company(
            session, context, company_id, expected_version=expected_version
        )
    except Exception as exc:
        _raise_http_error(exc)
        raise
    _etag(response, company.version)
    return CompanyResponse.from_model(company)
