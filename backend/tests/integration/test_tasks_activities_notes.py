from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.config import Settings, get_settings
from mycrm.core.database import get_session
from mycrm.main import app
from mycrm.modules.activities.application import create_activity, list_activities
from mycrm.modules.activities.models import ActivityType
from mycrm.modules.crm_shared import RelatedEntityNotFoundError, VersionConflictError
from mycrm.modules.deals.application import create_deal
from mycrm.modules.identity.application import register_user
from mycrm.modules.notes.application import create_note, update_note
from mycrm.modules.pipelines.application import StageSpec, create_pipeline
from mycrm.modules.pipelines.models import StageOutcome
from mycrm.modules.tasks.application import change_task_status, create_task
from mycrm.modules.tasks.models import Task, TaskPriority, TaskStatus
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


async def _deal(database_session: AsyncSession, context: WorkspaceContext):  # type: ignore[no-untyped-def]
    pipeline = await create_pipeline(
        database_session,
        context,
        name=f"Sales {uuid4()}",
        stages=[StageSpec("Open", 20, StageOutcome.OPEN)],
    )
    return await create_deal(
        database_session,
        context,
        pipeline_id=pipeline.pipeline.id,
        stage_id=pipeline.stages[0].id,
        company_id=None,
        contact_id=None,
        title="Task-related deal",
        amount=Decimal("10.00"),
        currency="EUR",
        probability=None,
        expected_close_date=None,
    )


async def test_task_status_command_sets_completion_and_rejects_stale_version(
    database_session: AsyncSession,
) -> None:
    context = await _context(database_session, "Task Lifecycle")
    task = await create_task(
        database_session,
        context,
        title="Call the client",
        description=None,
        due_at=None,
        priority=TaskPriority.HIGH,
        assignee_id=context.actor_id,
        company_id=None,
        contact_id=None,
        deal_id=None,
    )

    completed = await change_task_status(
        database_session,
        context,
        task.id,
        target_status=TaskStatus.DONE,
        expected_version=1,
    )
    assert completed.status == TaskStatus.DONE
    assert completed.completed_at is not None
    assert completed.version == 2
    with pytest.raises(VersionConflictError):
        await change_task_status(
            database_session,
            context,
            task.id,
            target_status=TaskStatus.TODO,
            expected_version=1,
        )


async def test_related_deal_must_belong_to_the_same_workspace(
    database_session: AsyncSession,
) -> None:
    first = await _context(database_session, "Relation First")
    second = await _context(database_session, "Relation Second")
    foreign_deal = await _deal(database_session, second)

    with pytest.raises(RelatedEntityNotFoundError):
        await create_task(
            database_session,
            first,
            title="Forbidden relation",
            description=None,
            due_at=None,
            priority=TaskPriority.MEDIUM,
            assignee_id=None,
            company_id=None,
            contact_id=None,
            deal_id=foreign_deal.id,
        )

    with pytest.raises(IntegrityError):
        async with database_session.begin_nested():
            database_session.add(
                Task(
                    workspace_id=first.workspace_id,
                    deal_id=foreign_deal.id,
                    title="Database boundary",
                    priority=TaskPriority.MEDIUM,
                    status=TaskStatus.TODO,
                )
            )
            await database_session.flush()


async def test_activity_cursor_and_note_optimistic_locking(
    database_session: AsyncSession,
) -> None:
    context = await _context(database_session, "Timeline")
    now = datetime.now(UTC)
    for index in range(3):
        await create_activity(
            database_session,
            context,
            activity_type=ActivityType.CALL,
            summary=f"Call {index}",
            details=None,
            occurred_at=now - timedelta(hours=index),
            company_id=None,
            contact_id=None,
            deal_id=None,
        )

    first_page = await list_activities(
        database_session,
        context,
        company_id=None,
        contact_id=None,
        deal_id=None,
        cursor=None,
        limit=2,
    )
    assert [item.summary for item in first_page.items] == ["Call 0", "Call 1"]
    assert first_page.next_cursor is not None
    second_page = await list_activities(
        database_session,
        context,
        company_id=None,
        contact_id=None,
        deal_id=None,
        cursor=first_page.next_cursor,
        limit=2,
    )
    assert [item.summary for item in second_page.items] == ["Call 2"]

    note = await create_note(
        database_session,
        context,
        body="Original note",
        company_id=None,
        contact_id=None,
        deal_id=None,
    )
    changed = await update_note(
        database_session,
        context,
        note.id,
        body="Updated note",
        expected_version=1,
    )
    assert changed.body == "Updated note"
    assert changed.version == 2
    with pytest.raises(VersionConflictError):
        await update_note(
            database_session,
            context,
            note.id,
            body="Stale update",
            expected_version=1,
        )


async def test_task_activity_note_api_flow(database_session: AsyncSession) -> None:
    settings = Settings(
        _env_file=None,
        registration_enabled=True,
        secret_key="workflow-api-integration-secret",
    )

    async def override_session() -> AsyncSession:
        return database_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: settings
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            email = f"workflow-api-{uuid4()}@example.com"
            await client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "display_name": "Workflow API User",
                    "password": "a-strong-development-password",
                },
            )
            await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "a-strong-development-password"},
            )
            workspace_id = (await client.get("/api/v1/workspaces")).json()[0]["id"]
            headers = {"X-Workspace-ID": workspace_id}

            task_response = await client.post(
                "/api/v1/tasks",
                headers=headers,
                json={"title": "API follow-up", "priority": "urgent"},
            )
            assert task_response.status_code == 201
            task_id = task_response.json()["id"]
            completed = await client.post(
                f"/api/v1/tasks/{task_id}/change-status",
                headers=headers,
                json={"status": "done", "expected_version": 1},
            )
            assert completed.status_code == 200
            assert completed.json()["completed_at"] is not None

            activity_response = await client.post(
                "/api/v1/activities",
                headers=headers,
                json={
                    "activity_type": "call",
                    "summary": "API call",
                    "occurred_at": datetime.now(UTC).isoformat(),
                },
            )
            assert activity_response.status_code == 201
            assert activity_response.json()["source"] == "human"

            note_response = await client.post(
                "/api/v1/notes", headers=headers, json={"body": "API note"}
            )
            assert note_response.status_code == 201
            note_id = note_response.json()["id"]
            changed = await client.patch(
                f"/api/v1/notes/{note_id}",
                headers=headers,
                json={"body": "Changed API note", "expected_version": 1},
            )
            assert changed.status_code == 200
            assert changed.headers["etag"] == '"2"'

            paths = app.openapi()["paths"]
            assert set(paths["/api/v1/activities/{activity_id}"]) == {"get"}
    finally:
        app.dependency_overrides.clear()
