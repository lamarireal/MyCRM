from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.database import get_session
from mycrm.modules.crm_shared import (
    EntityNotFoundError,
    RelatedEntityMismatchError,
    RelatedEntityNotFoundError,
    VersionConflictError,
    WorkspaceWriteForbiddenError,
)
from mycrm.modules.deals.application import (
    DealChanges,
    archive_deal,
    create_deal,
    get_deal,
    list_deals,
    move_deal_stage,
    update_deal,
)
from mycrm.modules.deals.models import Deal, DealStatus
from mycrm.modules.workspaces.dependencies import CurrentWorkspace

router = APIRouter(prefix="/deals", tags=["deals"])


class DealCreateRequest(BaseModel):
    pipeline_id: UUID
    stage_id: UUID
    company_id: UUID | None = None
    contact_id: UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="EUR", min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    probability: int | None = Field(default=None, ge=0, le=100)
    expected_close_date: date | None = None


class DealUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    company_id: UUID | None = None
    contact_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    probability: int | None = Field(default=None, ge=0, le=100)
    expected_close_date: date | None = None

    @model_validator(mode="after")
    def require_change(self) -> "DealUpdateRequest":
        changed = self.model_fields_set - {"expected_version"}
        if not changed:
            raise ValueError("At least one field must be changed")
        for required in ("title", "currency", "probability"):
            if required in changed and getattr(self, required) is None:
                raise ValueError(f"{required} cannot be null")
        return self


class MoveStageRequest(BaseModel):
    stage_id: UUID
    expected_version: int = Field(ge=1)


class DealResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    pipeline_id: UUID
    stage_id: UUID
    company_id: UUID | None
    contact_id: UUID | None
    title: str
    amount: Decimal | None
    currency: str
    probability: int
    expected_close_date: date | None
    status: DealStatus
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, deal: Deal) -> "DealResponse":
        return cls.model_validate(deal, from_attributes=True)


class DealPageResponse(BaseModel):
    items: list[DealResponse]
    total: int
    limit: int
    offset: int


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


def _http_error(exc: Exception) -> None:
    if isinstance(exc, EntityNotFoundError):
        raise HTTPException(status_code=404, detail="Deal not found") from exc
    if isinstance(exc, RelatedEntityNotFoundError):
        raise HTTPException(status_code=404, detail="Related CRM record not found") from exc
    if isinstance(exc, RelatedEntityMismatchError):
        raise HTTPException(status_code=409, detail="Contact and company do not match") from exc
    if isinstance(exc, VersionConflictError):
        raise HTTPException(status_code=409, detail="Deal version conflict") from exc
    if isinstance(exc, WorkspaceWriteForbiddenError):
        raise HTTPException(status_code=403, detail="Workspace is read-only") from exc
    raise exc


@router.post("", response_model=DealResponse, status_code=status.HTTP_201_CREATED)
async def create(
    payload: DealCreateRequest,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DealResponse:
    try:
        deal = await create_deal(session, context, **payload.model_dump())
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, deal.version)
    return DealResponse.from_model(deal)


@router.get("", response_model=DealPageResponse)
async def list_all(
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
    search: Annotated[str | None, Query(max_length=200)] = None,
    pipeline_id: UUID | None = None,
    stage_id: UUID | None = None,
    deal_status: Annotated[DealStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DealPageResponse:
    page = await list_deals(
        session,
        context,
        search=search,
        pipeline_id=pipeline_id,
        stage_id=stage_id,
        status=deal_status,
        limit=limit,
        offset=offset,
    )
    return DealPageResponse(
        items=[DealResponse.from_model(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{deal_id}", response_model=DealResponse)
async def get_one(
    deal_id: UUID,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DealResponse:
    try:
        deal = await get_deal(session, context, deal_id)
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, deal.version)
    return DealResponse.from_model(deal)


@router.patch("/{deal_id}", response_model=DealResponse)
async def update_one(
    deal_id: UUID,
    payload: DealUpdateRequest,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DealResponse:
    changes: dict[str, Any] = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    try:
        deal = await update_deal(
            session,
            context,
            deal_id,
            expected_version=payload.expected_version,
            changes=cast(DealChanges, changes),
        )
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, deal.version)
    return DealResponse.from_model(deal)


@router.post("/{deal_id}/move-stage", response_model=DealResponse)
async def move_stage(
    deal_id: UUID,
    payload: MoveStageRequest,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DealResponse:
    try:
        deal = await move_deal_stage(
            session,
            context,
            deal_id,
            stage_id=payload.stage_id,
            expected_version=payload.expected_version,
        )
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, deal.version)
    return DealResponse.from_model(deal)


@router.delete("/{deal_id}", response_model=DealResponse)
async def archive_one(
    deal_id: UUID,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
    expected_version: Annotated[int, Query(ge=1)],
) -> DealResponse:
    try:
        deal = await archive_deal(session, context, deal_id, expected_version=expected_version)
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, deal.version)
    return DealResponse.from_model(deal)
