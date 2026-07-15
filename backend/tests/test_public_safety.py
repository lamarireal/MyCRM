from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from mycrm.main import app
from mycrm.modules.workspaces.domain import (
    WorkspaceAccessDeniedError,
    WorkspaceContext,
    WorkspaceKind,
    WorkspaceRole,
    WorkspaceStatus,
)
from mycrm.modules.workspaces.policy import SideEffect, can_execute_external_side_effect


async def test_oversized_request_is_rejected_before_routing() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/missing",
            content=b"x" * 1_048_577,
            headers={"content-type": "application/octet-stream"},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_demo_capabilities_are_safe_by_default() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/demo/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "read_only": True,
        "synthetic_data_only": True,
        "external_side_effects_enabled": False,
    }


def test_demo_workspace_cannot_execute_external_side_effects() -> None:
    context = WorkspaceContext(
        workspace_id=uuid4(),
        actor_id=None,
        role=WorkspaceRole.DEMO_VISITOR,
        kind=WorkspaceKind.DEMO,
        status=WorkspaceStatus.ACTIVE,
    )

    for effect in SideEffect:
        assert not can_execute_external_side_effect(context, effect)


def test_private_owner_can_execute_external_side_effects() -> None:
    actor_id = uuid4()
    context = WorkspaceContext(
        workspace_id=uuid4(),
        actor_id=actor_id,
        role=WorkspaceRole.OWNER,
        kind=WorkspaceKind.PRIVATE,
        status=WorkspaceStatus.ACTIVE,
    )

    assert can_execute_external_side_effect(context, SideEffect.SEND_EMAIL)


def test_workspace_context_rejects_an_entity_from_another_workspace() -> None:
    context = WorkspaceContext(
        workspace_id=uuid4(),
        actor_id=uuid4(),
        role=WorkspaceRole.MEMBER,
        kind=WorkspaceKind.TEAM,
        status=WorkspaceStatus.ACTIVE,
    )

    try:
        context.assert_scope(uuid4())
    except WorkspaceAccessDeniedError:
        pass
    else:
        raise AssertionError("Cross-workspace entity access must be rejected")
