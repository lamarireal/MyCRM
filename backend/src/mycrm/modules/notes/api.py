from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.database import get_session
from mycrm.modules.crm_shared import (
    EntityNotFoundError,
    RecordStatus,
    RelatedEntityNotFoundError,
    VersionConflictError,
    WorkspaceWriteForbiddenError,
)
from mycrm.modules.notes.application import (
    archive_note,
    create_note,
    get_note,
    list_notes,
    update_note,
)
from mycrm.modules.notes.models import Note
from mycrm.modules.workspaces.dependencies import CurrentWorkspace

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)
    company_id: UUID | None = None
    contact_id: UUID | None = None
    deal_id: UUID | None = None


class NoteUpdateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)
    expected_version: int = Field(ge=1)


class NoteResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    company_id: UUID | None
    contact_id: UUID | None
    deal_id: UUID | None
    author_id: UUID | None
    body: str
    normalized_body: str | None
    status: RecordStatus
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, note: Note) -> "NoteResponse":
        return cls.model_validate(note, from_attributes=True)


class NotePageResponse(BaseModel):
    items: list[NoteResponse]
    total: int
    limit: int
    offset: int


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


def _http_error(exc: Exception) -> None:
    if isinstance(exc, EntityNotFoundError):
        raise HTTPException(status_code=404, detail="Note not found") from exc
    if isinstance(exc, RelatedEntityNotFoundError):
        raise HTTPException(status_code=404, detail="Related CRM record not found") from exc
    if isinstance(exc, VersionConflictError):
        raise HTTPException(status_code=409, detail="Note version conflict") from exc
    if isinstance(exc, WorkspaceWriteForbiddenError):
        raise HTTPException(status_code=403, detail="Workspace is read-only") from exc
    raise exc


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create(
    payload: NoteCreateRequest,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NoteResponse:
    try:
        note = await create_note(session, context, **payload.model_dump())
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, note.version)
    return NoteResponse.from_model(note)


@router.get("", response_model=NotePageResponse)
async def list_all(
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
    company_id: UUID | None = None,
    contact_id: UUID | None = None,
    deal_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NotePageResponse:
    page = await list_notes(
        session,
        context,
        company_id=company_id,
        contact_id=contact_id,
        deal_id=deal_id,
        limit=limit,
        offset=offset,
    )
    return NotePageResponse(
        items=[NoteResponse.from_model(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{note_id}", response_model=NoteResponse)
async def get_one(
    note_id: UUID,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NoteResponse:
    try:
        note = await get_note(session, context, note_id)
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, note.version)
    return NoteResponse.from_model(note)


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_one(
    note_id: UUID,
    payload: NoteUpdateRequest,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NoteResponse:
    try:
        note = await update_note(
            session,
            context,
            note_id,
            body=payload.body,
            expected_version=payload.expected_version,
        )
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, note.version)
    return NoteResponse.from_model(note)


@router.delete("/{note_id}", response_model=NoteResponse)
async def archive_one(
    note_id: UUID,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
    expected_version: Annotated[int, Query(ge=1)],
) -> NoteResponse:
    try:
        note = await archive_note(session, context, note_id, expected_version=expected_version)
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, note.version)
    return NoteResponse.from_model(note)
