from datetime import datetime
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.database import get_session
from mycrm.modules.crm_shared import (
    EntityNotFoundError,
    StageOperationError,
    VersionConflictError,
    WorkspaceWriteForbiddenError,
)
from mycrm.modules.pipelines.application import (
    PipelineDetails,
    StageChanges,
    StageSpec,
    archive_stage,
    create_pipeline,
    get_pipeline,
    list_pipelines,
    reorder_stages,
    update_stage,
)
from mycrm.modules.pipelines.models import Pipeline, PipelineStage, StageOutcome
from mycrm.modules.workspaces.dependencies import CurrentWorkspace

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


class StageCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    probability: int = Field(ge=0, le=100)
    outcome: StageOutcome = StageOutcome.OPEN


class PipelineCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    stages: list[StageCreateRequest] = Field(min_length=2, max_length=30)

    @model_validator(mode="after")
    def validate_stage_names(self) -> "PipelineCreateRequest":
        names = [stage.name.strip().casefold() for stage in self.stages]
        if len(names) != len(set(names)):
            raise ValueError("Stage names must be unique inside a pipeline")
        return self


class StageUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    probability: int | None = Field(default=None, ge=0, le=100)
    outcome: StageOutcome | None = None

    @model_validator(mode="after")
    def require_change(self) -> "StageUpdateRequest":
        changed = self.model_fields_set - {"expected_version"}
        if not changed:
            raise ValueError("At least one field must be changed")
        for field_name in changed:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class StageReorderRequest(BaseModel):
    expected_pipeline_version: int = Field(ge=1)
    stage_ids: list[UUID] = Field(min_length=2, max_length=30)


class StageArchiveRequest(BaseModel):
    expected_pipeline_version: int = Field(ge=1)
    expected_stage_version: int = Field(ge=1)
    replacement_stage_id: UUID | None = None


class StageResponse(BaseModel):
    id: UUID
    name: str
    position: int
    probability: int
    outcome: StageOutcome
    version: int

    @classmethod
    def from_model(cls, stage: PipelineStage) -> "StageResponse":
        if stage.position is None:
            raise ValueError("An active stage must have a position")
        return cls(
            id=stage.id,
            name=stage.name,
            position=stage.position,
            probability=stage.probability,
            outcome=stage.outcome,
            version=stage.version,
        )


class PipelineSummaryResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    version: int
    created_at: datetime

    @classmethod
    def from_model(cls, pipeline: Pipeline) -> "PipelineSummaryResponse":
        return cls(
            id=pipeline.id,
            workspace_id=pipeline.workspace_id,
            name=pipeline.name,
            version=pipeline.version,
            created_at=pipeline.created_at,
        )


class PipelineResponse(PipelineSummaryResponse):
    stages: list[StageResponse]

    @classmethod
    def from_details(cls, details: PipelineDetails) -> "PipelineResponse":
        pipeline = details.pipeline
        return cls(
            id=pipeline.id,
            workspace_id=pipeline.workspace_id,
            name=pipeline.name,
            version=pipeline.version,
            created_at=pipeline.created_at,
            stages=[StageResponse.from_model(stage) for stage in details.stages],
        )


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


def _http_error(exc: Exception) -> None:
    if isinstance(exc, EntityNotFoundError):
        raise HTTPException(status_code=404, detail="Pipeline or stage not found") from exc
    if isinstance(exc, VersionConflictError):
        raise HTTPException(status_code=409, detail="Pipeline or stage version conflict") from exc
    if isinstance(exc, StageOperationError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, WorkspaceWriteForbiddenError):
        raise HTTPException(status_code=403, detail="Workspace is read-only") from exc
    raise exc


@router.post("", response_model=PipelineResponse, status_code=status.HTTP_201_CREATED)
async def create(
    payload: PipelineCreateRequest,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PipelineResponse:
    try:
        details = await create_pipeline(
            session,
            context,
            name=payload.name,
            stages=[
                StageSpec(stage.name, stage.probability, stage.outcome) for stage in payload.stages
            ],
        )
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, details.pipeline.version)
    return PipelineResponse.from_details(details)


@router.get("", response_model=list[PipelineSummaryResponse])
async def list_all(
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[PipelineSummaryResponse]:
    return [
        PipelineSummaryResponse.from_model(item) for item in await list_pipelines(session, context)
    ]


@router.get("/{pipeline_id}", response_model=PipelineResponse)
async def get_one(
    pipeline_id: UUID,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PipelineResponse:
    try:
        details = await get_pipeline(session, context, pipeline_id)
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, details.pipeline.version)
    return PipelineResponse.from_details(details)


@router.patch("/{pipeline_id}/stages/{stage_id}", response_model=StageResponse)
async def update_stage_metadata(
    pipeline_id: UUID,
    stage_id: UUID,
    payload: StageUpdateRequest,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StageResponse:
    changes: dict[str, Any] = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    try:
        stage = await update_stage(
            session,
            context,
            pipeline_id,
            stage_id,
            expected_version=payload.expected_version,
            changes=cast(StageChanges, changes),
        )
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, stage.version)
    return StageResponse.from_model(stage)


@router.post("/{pipeline_id}/reorder-stages", response_model=PipelineResponse)
async def reorder(
    pipeline_id: UUID,
    payload: StageReorderRequest,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PipelineResponse:
    try:
        details = await reorder_stages(
            session,
            context,
            pipeline_id,
            expected_version=payload.expected_pipeline_version,
            stage_ids=payload.stage_ids,
        )
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, details.pipeline.version)
    return PipelineResponse.from_details(details)


@router.post("/{pipeline_id}/stages/{stage_id}/archive", response_model=PipelineResponse)
async def archive(
    pipeline_id: UUID,
    stage_id: UUID,
    payload: StageArchiveRequest,
    response: Response,
    context: CurrentWorkspace,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PipelineResponse:
    try:
        details = await archive_stage(
            session,
            context,
            pipeline_id,
            stage_id,
            expected_pipeline_version=payload.expected_pipeline_version,
            expected_stage_version=payload.expected_stage_version,
            replacement_stage_id=payload.replacement_stage_id,
        )
    except Exception as exc:
        _http_error(exc)
        raise
    _etag(response, details.pipeline.version)
    return PipelineResponse.from_details(details)
