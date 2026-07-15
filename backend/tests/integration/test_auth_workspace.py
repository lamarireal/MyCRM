from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.config import Settings, get_settings
from mycrm.core.database import get_session
from mycrm.main import app
from mycrm.modules.identity.application import (
    authenticate_user,
    register_user,
    resolve_user_session,
)
from mycrm.modules.identity.security import hash_session_token
from mycrm.modules.workspaces.application import (
    WorkspaceNotAccessibleError,
    list_accessible_workspaces,
    resolve_member_workspace,
)


async def test_registration_creates_a_private_owner_workspace(
    database_session: AsyncSession,
) -> None:
    user = await register_user(
        database_session,
        email=f"owner-{uuid4()}@example.com",
        display_name="Portfolio Owner",
        password="a-strong-development-password",
    )

    workspaces = await list_accessible_workspaces(database_session, user)

    assert len(workspaces) == 1
    workspace, membership = workspaces[0]
    assert workspace.kind.value == "private"
    assert membership.role.value == "owner"
    assert membership.workspace_id == workspace.id


async def test_member_cannot_resolve_another_users_workspace(
    database_session: AsyncSession,
) -> None:
    first_user = await register_user(
        database_session,
        email=f"first-{uuid4()}@example.com",
        display_name="First User",
        password="a-strong-development-password",
    )
    second_user = await register_user(
        database_session,
        email=f"second-{uuid4()}@example.com",
        display_name="Second User",
        password="a-strong-development-password",
    )
    second_workspace = (await list_accessible_workspaces(database_session, second_user))[0][0]

    with pytest.raises(WorkspaceNotAccessibleError):
        await resolve_member_workspace(database_session, first_user, second_workspace.id)


async def test_login_stores_only_a_token_hash_and_resolves_the_session(
    database_session: AsyncSession,
) -> None:
    email = f"login-{uuid4()}@example.com"
    user = await register_user(
        database_session,
        email=email,
        display_name="Login User",
        password="a-strong-development-password",
    )
    settings = Settings(_env_file=None, secret_key="test-session-secret")

    created = await authenticate_user(
        database_session,
        settings,
        email=email,
        password="a-strong-development-password",
    )
    resolved_user, auth_session = await resolve_user_session(
        database_session, settings, created.token
    )

    assert resolved_user.id == user.id
    assert auth_session.token_hash == hash_session_token(created.token, "test-session-secret")
    assert auth_session.token_hash != created.token


async def test_authentication_and_workspace_api_flow(database_session: AsyncSession) -> None:
    settings = Settings(
        _env_file=None,
        registration_enabled=True,
        secret_key="integration-session-secret",
    )

    async def override_session() -> AsyncSession:
        return database_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: settings
    email = f"api-{uuid4()}@example.com"
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            registration = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "display_name": "API User",
                    "password": "a-strong-development-password",
                },
            )
            assert registration.status_code == 201

            login = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "a-strong-development-password"},
            )
            assert login.status_code == 200
            assert "HttpOnly" in login.headers["set-cookie"]

            workspaces = await client.get("/api/v1/workspaces")
            assert workspaces.status_code == 200
            workspace_id = workspaces.json()[0]["id"]

            current = await client.get(
                "/api/v1/workspaces/current",
                headers={"X-Workspace-ID": workspace_id},
            )
            assert current.status_code == 200
            assert current.json()["role"] == "owner"
            assert current.json()["can_write"] is True

            forbidden = await client.get(
                "/api/v1/workspaces/current",
                headers={"X-Workspace-ID": str(uuid4())},
            )
            assert forbidden.status_code == 404

            logout = await client.post("/api/v1/auth/logout")
            assert logout.status_code == 204
            assert (await client.get("/api/v1/auth/me")).status_code == 401
    finally:
        app.dependency_overrides.clear()
