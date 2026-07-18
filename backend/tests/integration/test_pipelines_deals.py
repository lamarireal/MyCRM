from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.config import Settings, get_settings
from mycrm.core.database import get_session
from mycrm.main import app
from mycrm.modules.crm_shared import (
    EntityNotFoundError,
    RelatedEntityNotFoundError,
    VersionConflictError,
)
from mycrm.modules.deals.application import create_deal, move_deal_stage
from mycrm.modules.deals.models import Deal, DealStatus
from mycrm.modules.identity.application import register_user
from mycrm.modules.pipelines.application import StageSpec, create_pipeline, get_pipeline
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
        StageSpec("Qualified", 25, StageOutcome.OPEN),
        StageSpec("Proposal", 60, StageOutcome.OPEN),
        StageSpec("Won", 100, StageOutcome.WON),
        StageSpec("Lost", 0, StageOutcome.LOST),
    ]


async def test_pipeline_stages_are_ordered_and_workspace_scoped(
    database_session: AsyncSession,
) -> None:
    first = await _context(database_session, "Pipeline First")
    second = await _context(database_session, "Pipeline Second")
    created = await create_pipeline(database_session, first, name="Sales", stages=_stages())

    assert [stage.position for stage in created.stages] == [1, 2, 3, 4]
    assert [stage.name for stage in created.stages] == ["Qualified", "Proposal", "Won", "Lost"]
    assert (
        await get_pipeline(database_session, first, created.pipeline.id)
    ).pipeline.id == created.pipeline.id
    with pytest.raises(EntityNotFoundError):
        await get_pipeline(database_session, second, created.pipeline.id)


async def test_move_stage_updates_status_probability_and_version(
    database_session: AsyncSession,
) -> None:
    context = await _context(database_session, "Deal Move")
    pipeline = await create_pipeline(database_session, context, name="Sales", stages=_stages())
    deal = await create_deal(
        database_session,
        context,
        pipeline_id=pipeline.pipeline.id,
        stage_id=pipeline.stages[0].id,
        company_id=None,
        contact_id=None,
        title="Exact money deal",
        amount=Decimal("1234.56"),
        currency="eur",
        probability=None,
        expected_close_date=None,
    )

    assert deal.amount == Decimal("1234.56")
    assert deal.probability == 25
    moved = await move_deal_stage(
        database_session,
        context,
        deal.id,
        stage_id=pipeline.stages[2].id,
        expected_version=1,
    )
    assert moved.status == DealStatus.WON
    assert moved.probability == 100
    assert moved.version == 2
    with pytest.raises(VersionConflictError):
        await move_deal_stage(
            database_session,
            context,
            deal.id,
            stage_id=pipeline.stages[1].id,
            expected_version=1,
        )


async def test_deal_cannot_use_a_pipeline_or_stage_from_another_workspace(
    database_session: AsyncSession,
) -> None:
    first = await _context(database_session, "Boundary First")
    second = await _context(database_session, "Boundary Second")
    foreign = await create_pipeline(database_session, second, name="Foreign", stages=_stages())

    with pytest.raises(RelatedEntityNotFoundError):
        await create_deal(
            database_session,
            first,
            pipeline_id=foreign.pipeline.id,
            stage_id=foreign.stages[0].id,
            company_id=None,
            contact_id=None,
            title="Forbidden",
            amount=None,
            currency="EUR",
            probability=None,
            expected_close_date=None,
        )

    with pytest.raises(IntegrityError):
        async with database_session.begin_nested():
            database_session.add(
                Deal(
                    workspace_id=first.workspace_id,
                    pipeline_id=foreign.pipeline.id,
                    stage_id=foreign.stages[0].id,
                    title="Database boundary",
                    amount=None,
                    currency="EUR",
                    probability=25,
                    status=DealStatus.OPEN,
                )
            )
            await database_session.flush()


async def test_pipeline_and_deal_api_flow(database_session: AsyncSession) -> None:
    settings = Settings(
        _env_file=None,
        registration_enabled=True,
        secret_key="pipeline-api-integration-secret",
    )

    async def override_session() -> AsyncSession:
        return database_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: settings
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            email = f"deal-api-{uuid4()}@example.com"
            await client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "display_name": "Deal API User",
                    "password": "a-strong-development-password",
                },
            )
            await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "a-strong-development-password"},
            )
            workspace_id = (await client.get("/api/v1/workspaces")).json()[0]["id"]
            headers = {"X-Workspace-ID": workspace_id}
            pipeline_response = await client.post(
                "/api/v1/pipelines",
                headers=headers,
                json={
                    "name": "API Sales",
                    "stages": [
                        {"name": "Open", "probability": 20},
                        {"name": "Won", "probability": 100, "outcome": "won"},
                    ],
                },
            )
            assert pipeline_response.status_code == 201
            pipeline = pipeline_response.json()
            deal_response = await client.post(
                "/api/v1/deals",
                headers=headers,
                json={
                    "pipeline_id": pipeline["id"],
                    "stage_id": pipeline["stages"][0]["id"],
                    "title": "API Deal",
                    "amount": "99.95",
                    "currency": "EUR",
                },
            )
            assert deal_response.status_code == 201
            assert deal_response.headers["etag"] == '"1"'
            deal_id = deal_response.json()["id"]
            moved = await client.post(
                f"/api/v1/deals/{deal_id}/move-stage",
                headers=headers,
                json={"stage_id": pipeline["stages"][1]["id"], "expected_version": 1},
            )
            assert moved.status_code == 200
            assert moved.json()["status"] == "won"
            assert moved.json()["version"] == 2
            assert (await client.get("/api/v1/deals?status=won", headers=headers)).json()[
                "total"
            ] == 1
    finally:
        app.dependency_overrides.clear()
