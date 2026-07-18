from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NoReturn, TypedDict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.modules.audit.application import model_snapshot, record_audit
from mycrm.modules.crm_shared import (
    EntityNotFoundError,
    RecordStatus,
    StageOperationError,
    VersionConflictError,
    require_workspace_write,
)
from mycrm.modules.deals.models import Deal, DealStatus
from mycrm.modules.pipelines.models import Pipeline, PipelineStage, StageOutcome
from mycrm.modules.workspaces.domain import WorkspaceContext


@dataclass(frozen=True, slots=True)
class StageSpec:
    name: str
    probability: int
    outcome: StageOutcome


@dataclass(frozen=True, slots=True)
class PipelineDetails:
    pipeline: Pipeline
    stages: list[PipelineStage]


class StageChanges(TypedDict, total=False):
    name: str
    probability: int
    outcome: StageOutcome


def _deal_status(outcome: StageOutcome) -> DealStatus:
    return {
        StageOutcome.OPEN: DealStatus.OPEN,
        StageOutcome.WON: DealStatus.WON,
        StageOutcome.LOST: DealStatus.LOST,
    }[outcome]


async def create_pipeline(
    session: AsyncSession,
    context: WorkspaceContext,
    *,
    name: str,
    stages: list[StageSpec],
) -> PipelineDetails:
    require_workspace_write(context.can_write)
    pipeline = Pipeline(workspace_id=context.workspace_id, name=name.strip())
    session.add(pipeline)
    await session.flush()
    models = [
        PipelineStage(
            workspace_id=context.workspace_id,
            pipeline_id=pipeline.id,
            name=stage.name.strip(),
            position=position,
            probability=stage.probability,
            outcome=stage.outcome,
        )
        for position, stage in enumerate(stages, start=1)
    ]
    session.add_all(models)
    await session.flush()
    await session.refresh(pipeline)
    for stage in models:
        await session.refresh(stage)
        await record_audit(
            session,
            context,
            action="created",
            entity_type="pipeline_stage",
            entity_id=stage.id,
            before_state=None,
            after_state=model_snapshot(stage),
        )
    await record_audit(
        session,
        context,
        action="created",
        entity_type="pipeline",
        entity_id=pipeline.id,
        before_state=None,
        after_state={
            **model_snapshot(pipeline),
            "stage_order": [str(stage.id) for stage in models],
        },
    )
    return PipelineDetails(pipeline=pipeline, stages=models)


async def get_pipeline(
    session: AsyncSession, context: WorkspaceContext, pipeline_id: UUID
) -> PipelineDetails:
    pipeline = await session.scalar(
        select(Pipeline).where(
            Pipeline.workspace_id == context.workspace_id,
            Pipeline.id == pipeline_id,
            Pipeline.status == RecordStatus.ACTIVE,
        )
    )
    if pipeline is None:
        raise EntityNotFoundError
    stages = list(
        (
            await session.scalars(
                select(PipelineStage)
                .where(
                    PipelineStage.workspace_id == context.workspace_id,
                    PipelineStage.pipeline_id == pipeline.id,
                    PipelineStage.status == RecordStatus.ACTIVE,
                )
                .order_by(PipelineStage.position)
            )
        ).all()
    )
    return PipelineDetails(pipeline=pipeline, stages=stages)


async def list_pipelines(session: AsyncSession, context: WorkspaceContext) -> list[Pipeline]:
    return list(
        (
            await session.scalars(
                select(Pipeline)
                .where(
                    Pipeline.workspace_id == context.workspace_id,
                    Pipeline.status == RecordStatus.ACTIVE,
                )
                .order_by(Pipeline.name, Pipeline.id)
            )
        ).all()
    )


async def _locked_pipeline(
    session: AsyncSession,
    context: WorkspaceContext,
    pipeline_id: UUID,
    *,
    expected_version: int | None = None,
) -> Pipeline:
    pipeline = await session.scalar(
        select(Pipeline)
        .where(
            Pipeline.workspace_id == context.workspace_id,
            Pipeline.id == pipeline_id,
            Pipeline.status == RecordStatus.ACTIVE,
        )
        .with_for_update()
    )
    if pipeline is None:
        raise EntityNotFoundError
    if expected_version is not None and pipeline.version != expected_version:
        raise VersionConflictError
    return pipeline


async def _active_stages_locked(
    session: AsyncSession, context: WorkspaceContext, pipeline_id: UUID
) -> list[PipelineStage]:
    return list(
        (
            await session.scalars(
                select(PipelineStage)
                .where(
                    PipelineStage.workspace_id == context.workspace_id,
                    PipelineStage.pipeline_id == pipeline_id,
                    PipelineStage.status == RecordStatus.ACTIVE,
                )
                .order_by(PipelineStage.position)
                .with_for_update()
            )
        ).all()
    )


async def _stage_failure(
    session: AsyncSession,
    context: WorkspaceContext,
    pipeline_id: UUID,
    stage_id: UUID,
) -> NoReturn:
    version = await session.scalar(
        select(PipelineStage.version).where(
            PipelineStage.workspace_id == context.workspace_id,
            PipelineStage.pipeline_id == pipeline_id,
            PipelineStage.id == stage_id,
            PipelineStage.status == RecordStatus.ACTIVE,
        )
    )
    if version is None:
        raise EntityNotFoundError
    raise VersionConflictError


async def update_stage(
    session: AsyncSession,
    context: WorkspaceContext,
    pipeline_id: UUID,
    stage_id: UUID,
    *,
    expected_version: int,
    changes: StageChanges,
) -> PipelineStage:
    require_workspace_write(context.can_write)
    await _locked_pipeline(session, context, pipeline_id)
    stage = await session.scalar(
        select(PipelineStage)
        .where(
            PipelineStage.workspace_id == context.workspace_id,
            PipelineStage.pipeline_id == pipeline_id,
            PipelineStage.id == stage_id,
            PipelineStage.status == RecordStatus.ACTIVE,
        )
        .with_for_update()
    )
    if stage is None:
        raise EntityNotFoundError
    if stage.version != expected_version:
        raise VersionConflictError
    if "name" in changes:
        duplicate = await session.scalar(
            select(PipelineStage.id).where(
                PipelineStage.workspace_id == context.workspace_id,
                PipelineStage.pipeline_id == pipeline_id,
                PipelineStage.id != stage_id,
                PipelineStage.status == RecordStatus.ACTIVE,
                func.lower(PipelineStage.name) == changes["name"].strip().lower(),
            )
        )
        if duplicate is not None:
            raise StageOperationError("Stage names must be unique inside a pipeline")
    if "outcome" in changes and changes["outcome"] != stage.outcome:
        active_deals = await session.scalar(
            select(func.count(Deal.id)).where(
                Deal.workspace_id == context.workspace_id,
                Deal.pipeline_id == pipeline_id,
                Deal.stage_id == stage_id,
                Deal.status != DealStatus.ARCHIVED,
            )
        )
        if active_deals:
            raise StageOperationError(
                "A stage outcome cannot change while active deals use the stage"
            )
    before = model_snapshot(stage)
    if "name" in changes:
        stage.name = changes["name"].strip()
    if "probability" in changes:
        stage.probability = changes["probability"]
    if "outcome" in changes:
        stage.outcome = changes["outcome"]
    stage.version += 1
    stage.updated_at = datetime.now(UTC)
    await session.flush()
    await record_audit(
        session,
        context,
        action="updated",
        entity_type="pipeline_stage",
        entity_id=stage.id,
        before_state=before,
        after_state=model_snapshot(stage),
    )
    return stage


async def reorder_stages(
    session: AsyncSession,
    context: WorkspaceContext,
    pipeline_id: UUID,
    *,
    expected_version: int,
    stage_ids: list[UUID],
) -> PipelineDetails:
    require_workspace_write(context.can_write)
    pipeline = await _locked_pipeline(
        session, context, pipeline_id, expected_version=expected_version
    )
    stages = await _active_stages_locked(session, context, pipeline_id)
    current_ids = [stage.id for stage in stages]
    if len(stage_ids) != len(set(stage_ids)) or set(stage_ids) != set(current_ids):
        raise StageOperationError("The complete active stage order is required")
    if stage_ids == current_ids:
        return PipelineDetails(pipeline=pipeline, stages=stages)
    before_order = [str(stage_id) for stage_id in current_ids]
    by_id = {stage.id: stage for stage in stages}
    snapshots = {stage.id: model_snapshot(stage) for stage in stages}
    for stage in stages:
        if stage.position is None:
            raise StageOperationError("Active stages must have a position")
        stage.position += 1_000_000
    await session.flush()
    ordered = [by_id[stage_id] for stage_id in stage_ids]
    for position, stage in enumerate(ordered, start=1):
        stage.position = position
        stage.version += 1
        stage.updated_at = datetime.now(UTC)
    pipeline.version += 1
    pipeline.updated_at = datetime.now(UTC)
    await session.flush()
    for stage in ordered:
        await record_audit(
            session,
            context,
            action="reordered",
            entity_type="pipeline_stage",
            entity_id=stage.id,
            before_state=snapshots[stage.id],
            after_state=model_snapshot(stage),
        )
    await record_audit(
        session,
        context,
        action="stages_reordered",
        entity_type="pipeline",
        entity_id=pipeline.id,
        before_state={"version": expected_version, "stage_order": before_order},
        after_state={
            "version": pipeline.version,
            "stage_order": [str(stage_id) for stage_id in stage_ids],
        },
    )
    return PipelineDetails(pipeline=pipeline, stages=ordered)


async def archive_stage(
    session: AsyncSession,
    context: WorkspaceContext,
    pipeline_id: UUID,
    stage_id: UUID,
    *,
    expected_pipeline_version: int,
    expected_stage_version: int,
    replacement_stage_id: UUID | None,
) -> PipelineDetails:
    require_workspace_write(context.can_write)
    pipeline = await _locked_pipeline(
        session,
        context,
        pipeline_id,
        expected_version=expected_pipeline_version,
    )
    stages = await _active_stages_locked(session, context, pipeline_id)
    if len(stages) <= 2:
        raise StageOperationError("A pipeline must keep at least two active stages")
    by_id = {stage.id: stage for stage in stages}
    stage = by_id.get(stage_id)
    if stage is None:
        raise EntityNotFoundError
    if stage.version != expected_stage_version:
        raise VersionConflictError
    replacement = by_id.get(replacement_stage_id) if replacement_stage_id is not None else None
    if replacement_stage_id == stage_id or (
        replacement_stage_id is not None and replacement is None
    ):
        raise StageOperationError("Replacement must be another active stage in this pipeline")
    deals = list(
        (
            await session.scalars(
                select(Deal)
                .where(
                    Deal.workspace_id == context.workspace_id,
                    Deal.pipeline_id == pipeline_id,
                    Deal.stage_id == stage_id,
                    Deal.status != DealStatus.ARCHIVED,
                )
                .with_for_update()
            )
        ).all()
    )
    if deals and replacement is None:
        raise StageOperationError(
            "A replacement stage is required while active deals use this stage"
        )

    stage_snapshots = {item.id: model_snapshot(item) for item in stages}
    for deal in deals:
        before = model_snapshot(deal)
        assert replacement is not None
        deal.stage_id = replacement.id
        deal.probability = replacement.probability
        deal.status = _deal_status(replacement.outcome)
        deal.version += 1
        deal.updated_at = datetime.now(UTC)
        await record_audit(
            session,
            context,
            action="stage_reassigned",
            entity_type="deal",
            entity_id=deal.id,
            before_state=before,
            after_state=model_snapshot(deal),
        )

    remaining = [item for item in stages if item.id != stage_id]
    stage.position = None
    stage.status = RecordStatus.ARCHIVED
    stage.version += 1
    stage.updated_at = datetime.now(UTC)
    await session.flush()
    for item in remaining:
        if item.position is None:
            raise StageOperationError("Active stages must have a position")
        item.position += 1_000_000
    await session.flush()
    for position, item in enumerate(remaining, start=1):
        item.position = position
        if stage_snapshots[item.id]["position"] != position:
            item.version += 1
            item.updated_at = datetime.now(UTC)
    pipeline.version += 1
    pipeline.updated_at = datetime.now(UTC)
    await session.flush()

    for item in stages:
        await session.refresh(item)
        action = "archived" if item.id == stage_id else "reordered"
        after = model_snapshot(item)
        if after != stage_snapshots[item.id]:
            await record_audit(
                session,
                context,
                action=action,
                entity_type="pipeline_stage",
                entity_id=item.id,
                before_state=stage_snapshots[item.id],
                after_state=after,
            )
    await record_audit(
        session,
        context,
        action="stage_archived",
        entity_type="pipeline",
        entity_id=pipeline.id,
        before_state={"version": expected_pipeline_version, "archived_stage_id": str(stage_id)},
        after_state={
            "version": pipeline.version,
            "replacement_stage_id": str(replacement_stage_id) if replacement_stage_id else None,
            "moved_deal_count": len(deals),
        },
    )
    return PipelineDetails(pipeline=pipeline, stages=remaining)
