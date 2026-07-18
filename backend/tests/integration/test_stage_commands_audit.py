from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.config import Settings, get_settings
from mycrm.core.database import get_session
from mycrm.main import app
from mycrm.modules.audit.application import get_audit_record, list_audit_records
from mycrm.modules.audit.models import AuditRecord
from mycrm.modules.crm_shared import EntityNotFoundError, StageOperationError, VersionConflictError
from mycrm.modules.deals.application import create_deal, get_deal
from mycrm.modules.identity.application import register_user
from mycrm.modules.pipelines.application import (
    StageChanges,
    StageSpec,
    archive_stage,
    create_pipeline,
    reorder_stages,
    update_stage,
)
from mycrm.modules.pipelines.models import StageOutcome
from mycrm.modules.workspaces.application import (
    list_accessible_workspaces,
    resolve_member_workspace,
)
from mycrm.modules.workspaces.domain import WorkspaceContext


async def _context(database_session: AsyncSession, label: str) -> WorkspaceContext:
    user = await register_user(
        database_session,
        email=f"{label}-{uuid4()}@example.com",
        display_name=label,
        password="a-strong-development-password",
    )
    workspace = (await list_accessible_workspaces(database_session, user))[0][0]
    return await resolve_member_workspace(database_session, user, workspace.id)


def _stages() -> list[StageSpec]:
    return [
        StageSpec("Qualified", 20, StageOutcome.OPEN),
        StageSpec("Proposal", 60, StageOutcome.OPEN),
        StageSpec("Won", 100, StageOutcome.WON),
        StageSpec("Lost", 0, StageOutcome.LOST),
    ]


async def test_reorder_is_atomic_versioned_and_audited(database_session: AsyncSession) -> None:
    context = await _context(database_session, "Reorder")
    details = await create_pipeline(database_session, context, name="Sales", stages=_stages())
    reversed_ids = [stage.id for stage in reversed(details.stages)]

    reordered = await reorder_stages(
        database_session,
        context,
        details.pipeline.id,
        expected_version=1,
        stage_ids=reversed_ids,
    )

    assert [stage.id for stage in reordered.stages] == reversed_ids
    assert [stage.position for stage in reordered.stages] == [1, 2, 3, 4]
    assert reordered.pipeline.version == 2
    with pytest.raises(VersionConflictError):
        await reorder_stages(
            database_session,
            context,
            details.pipeline.id,
            expected_version=1,
            stage_ids=list(reversed(reversed_ids)),
        )

    page = await list_audit_records(
        database_session,
        context,
        entity_type="pipeline",
        entity_id=details.pipeline.id,
        cursor=None,
        limit=20,
    )
    assert [record.action for record in page.items][:2] == ["stages_reordered", "created"]


async def test_stage_outcome_change_is_blocked_when_active_deals_exist(
    database_session: AsyncSession,
) -> None:
    context = await _context(database_session, "Outcome")
    details = await create_pipeline(database_session, context, name="Sales", stages=_stages())
    stage = details.stages[0]
    await create_deal(
        database_session,
        context,
        pipeline_id=details.pipeline.id,
        stage_id=stage.id,
        company_id=None,
        contact_id=None,
        title="Active deal",
        amount=Decimal("100.00"),
        currency="EUR",
        probability=None,
        expected_close_date=None,
    )

    with pytest.raises(StageOperationError):
        await update_stage(
            database_session,
            context,
            details.pipeline.id,
            stage.id,
            expected_version=1,
            changes=StageChanges(outcome=StageOutcome.WON),
        )


async def test_archive_stage_moves_deals_and_compacts_positions(
    database_session: AsyncSession,
) -> None:
    context = await _context(database_session, "Archive Stage")
    details = await create_pipeline(database_session, context, name="Sales", stages=_stages())
    source = details.stages[1]
    replacement = details.stages[2]
    deal = await create_deal(
        database_session,
        context,
        pipeline_id=details.pipeline.id,
        stage_id=source.id,
        company_id=None,
        contact_id=None,
        title="Move on archive",
        amount=None,
        currency="EUR",
        probability=None,
        expected_close_date=None,
    )

    with pytest.raises(StageOperationError):
        await archive_stage(
            database_session,
            context,
            details.pipeline.id,
            source.id,
            expected_pipeline_version=1,
            expected_stage_version=1,
            replacement_stage_id=None,
        )

    result = await archive_stage(
        database_session,
        context,
        details.pipeline.id,
        source.id,
        expected_pipeline_version=1,
        expected_stage_version=1,
        replacement_stage_id=replacement.id,
    )
    moved = await get_deal(database_session, context, deal.id)
    assert moved.stage_id == replacement.id
    assert moved.status.value == "won"
    assert moved.probability == 100
    assert moved.version == 2
    assert [stage.position for stage in result.stages] == [1, 2, 3]
    assert source.position is None
    assert source.status.value == "archived"


async def test_audit_is_workspace_scoped_and_database_immutable(
    database_session: AsyncSession,
) -> None:
    first = await _context(database_session, "Audit First")
    second = await _context(database_session, "Audit Second")
    await create_pipeline(database_session, first, name="Sales", stages=_stages())
    record = await database_session.scalar(
        select(AuditRecord)
        .where(AuditRecord.workspace_id == first.workspace_id)
        .order_by(AuditRecord.created_at.desc(), AuditRecord.id)
    )
    assert record is not None
    with pytest.raises(EntityNotFoundError):
        await get_audit_record(database_session, second, record.id)

    with pytest.raises(DBAPIError):
        async with database_session.begin_nested():
            await database_session.execute(
                update(AuditRecord).where(AuditRecord.id == record.id).values(action="tampered")
            )


async def test_stage_commands_and_audit_api(database_session: AsyncSession) -> None:
    settings = Settings(
        _env_file=None,
        registration_enabled=True,
        secret_key="stage-audit-api-integration-secret",
    )

    async def override_session() -> AsyncSession:
        return database_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = f"stage-api-{uuid4()}@example.com"
            await client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "display_name": "Stage API User",
                    "password": "a-strong-development-password",
                },
            )
            await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "a-strong-development-password"},
            )
            workspace_id = (await client.get("/api/v1/workspaces")).json()[0]["id"]
            headers = {"X-Workspace-ID": workspace_id}
            created = await client.post(
                "/api/v1/pipelines",
                headers=headers,
                json={
                    "name": "API Pipeline",
                    "stages": [
                        {"name": "Open", "probability": 20},
                        {"name": "Proposal", "probability": 60},
                        {"name": "Won", "probability": 100, "outcome": "won"},
                    ],
                },
            )
            assert created.status_code == 201
            pipeline = created.json()
            pipeline_id = pipeline["id"]
            first_stage = pipeline["stages"][0]
            changed = await client.patch(
                f"/api/v1/pipelines/{pipeline_id}/stages/{first_stage['id']}",
                headers=headers,
                json={"name": "Qualified", "expected_version": 1},
            )
            assert changed.status_code == 200
            assert changed.json()["name"] == "Qualified"
            stage_ids = [stage["id"] for stage in reversed(pipeline["stages"])]
            reordered = await client.post(
                f"/api/v1/pipelines/{pipeline_id}/reorder-stages",
                headers=headers,
                json={"expected_pipeline_version": 1, "stage_ids": stage_ids},
            )
            assert reordered.status_code == 200
            assert [stage["id"] for stage in reordered.json()["stages"]] == stage_ids
            audit = await client.get(
                f"/api/v1/audit-records?entity_type=pipeline&entity_id={pipeline_id}",
                headers=headers,
            )
            assert audit.status_code == 200
            assert [item["action"] for item in audit.json()["items"]][:2] == [
                "stages_reordered",
                "created",
            ]
            assert set(app.openapi()["paths"]["/api/v1/audit-records/{record_id}"]) == {"get"}
    finally:
        app.dependency_overrides.clear()
