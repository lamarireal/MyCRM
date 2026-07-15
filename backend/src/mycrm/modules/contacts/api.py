from datetime import datetime
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.database import get_session
from mycrm.modules.contacts.application import (
    ContactChanges,
    ContactSort,
    SortDirection,
    archive_contact,
    create_contact,
    get_contact,
    list_contacts,
    update_contact,
)
from mycrm.modules.contacts.models import Contact
from mycrm.modules.crm_shared import (
    EntityNotFoundError,
    RelatedEntityNotFoundError,
    VersionConflictError,
    WorkspaceWriteForbiddenError,
)
from mycrm.modules.workspaces.dependencies import CurrentWorkspace

router = APIRouter(prefix="/contacts", tags=["contacts"])


class ContactCreateRequest(BaseModel):
    company_id: UUID | None = None
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(default="", max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    job_title: str | None = Field(default=None, max_length=120)


class ContactUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    company_id: UUID | None = None
    first_name: str | None = Field(default=None, min_length=1, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    job_title: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def require_change(self) -> "ContactUpdateRequest":
        changed = self.model_fields_set - {"expected_version"}
        if not changed:
            raise ValueError("At least one field must be changed")
        if "first_name" in changed and self.first_name is None:
            raise ValueError("First name cannot be null")
        if "last_name" in changed and self.last_name is None:
            raise ValueError("Last name cannot be null")
        return self


class ContactResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    company_id: UUID | None
    first_name: str
    last_name: str
    email: EmailStr | None
    phone: str | None
    job_title: str | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, contact: Contact) -> "ContactResponse":
        return cls(
            id=contact.id,
            workspace_id=contact.workspace_id,
            company_id=contact.company_id,
            first_name=contact.first_name,
            last_name=contact.last_name,
            email=contact.email,
            phone=contact.phone,
            job_title=contact.job_title,
            status=contact.status.value,
            version=contact.version,
            created_at=contact.created_at,
            updated_at=contact.updated_at,
        )


class ContactPageResponse(BaseModel):
    items: list[ContactResponse]
    total: int
    limit: int
    offset: int


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, EntityNotFoundError):
        raise HTTPException(status_code=404, detail="Contact not found") from exc
    if isinstance(exc, RelatedEntityNotFoundError):
        raise HTTPException(status_code=404, detail="Company not found in workspace") from exc
    if isinstance(exc, VersionConflictError):
        raise HTTPException(status_code=409, detail="Contact version conflict") from exc
    if isinstance(exc, WorkspaceWriteForbiddenError):
        raise HTTPException(status_code=403, detail="Workspace is read-only") from exc
    raise exc


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create(
    payload: ContactCreateRequest,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ContactResponse:
    try:
        contact = await create_contact(
            session,
            context,
            company_id=payload.company_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=str(payload.email) if payload.email else None,
            phone=payload.phone,
            job_title=payload.job_title,
        )
    except Exception as exc:
        _raise_http_error(exc)
        raise
    _etag(response, contact.version)
    return ContactResponse.from_model(contact)


@router.get("", response_model=ContactPageResponse)
async def list_all(
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
    search: Annotated[str | None, Query(max_length=200)] = None,
    company_id: UUID | None = None,
    include_archived: bool = False,
    sort: ContactSort = ContactSort.NAME,
    direction: SortDirection = SortDirection.ASC,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ContactPageResponse:
    page = await list_contacts(
        session,
        context,
        search=search,
        company_id=company_id,
        include_archived=include_archived,
        sort=sort,
        direction=direction,
        limit=limit,
        offset=offset,
    )
    return ContactPageResponse(
        items=[ContactResponse.from_model(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_one(
    contact_id: UUID,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
    include_archived: bool = False,
) -> ContactResponse:
    try:
        contact = await get_contact(session, context, contact_id, include_archived=include_archived)
    except Exception as exc:
        _raise_http_error(exc)
        raise
    _etag(response, contact.version)
    return ContactResponse.from_model(contact)


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_one(
    contact_id: UUID,
    payload: ContactUpdateRequest,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ContactResponse:
    raw_changes: dict[str, Any] = payload.model_dump(
        exclude_unset=True, exclude={"expected_version"}
    )
    if "email" in raw_changes and raw_changes["email"] is not None:
        raw_changes["email"] = str(raw_changes["email"])
    try:
        contact = await update_contact(
            session,
            context,
            contact_id,
            expected_version=payload.expected_version,
            changes=cast(ContactChanges, raw_changes),
        )
    except Exception as exc:
        _raise_http_error(exc)
        raise
    _etag(response, contact.version)
    return ContactResponse.from_model(contact)


@router.delete("/{contact_id}", response_model=ContactResponse)
async def archive_one(
    contact_id: UUID,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
    expected_version: Annotated[int, Query(ge=1)],
) -> ContactResponse:
    try:
        contact = await archive_contact(
            session, context, contact_id, expected_version=expected_version
        )
    except Exception as exc:
        _raise_http_error(exc)
        raise
    _etag(response, contact.version)
    return ContactResponse.from_model(contact)
