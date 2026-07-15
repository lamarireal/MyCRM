from dataclasses import replace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.config import Settings, get_settings
from mycrm.core.database import get_session
from mycrm.main import app
from mycrm.modules.companies.application import (
    CompanySort,
    create_company,
    get_company,
    list_companies,
    update_company,
)
from mycrm.modules.companies.application import (
    SortDirection as CompanySortDirection,
)
from mycrm.modules.contacts.application import (
    ContactSort,
    SortDirection,
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
from mycrm.modules.identity.application import register_user
from mycrm.modules.workspaces.application import (
    list_accessible_workspaces,
    resolve_member_workspace,
)
from mycrm.modules.workspaces.domain import WorkspaceContext, WorkspaceRole


async def _create_context(database_session: AsyncSession, label: str) -> WorkspaceContext:
    user = await register_user(
        database_session,
        email=f"{label}-{uuid4()}@example.com",
        display_name=label,
        password="a-strong-development-password",
    )
    workspace = (await list_accessible_workspaces(database_session, user))[0][0]
    return await resolve_member_workspace(database_session, user, workspace.id)


async def test_company_and_contact_reads_are_workspace_scoped(
    database_session: AsyncSession,
) -> None:
    first = await _create_context(database_session, "First")
    second = await _create_context(database_session, "Second")
    company = await create_company(
        database_session,
        first,
        name="Acme",
        website="https://acme.example.com/",
        industry="Software",
    )
    contact = await create_contact(
        database_session,
        first,
        company_id=company.id,
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        phone=None,
        job_title="Founder",
    )

    assert (await get_company(database_session, first, company.id)).id == company.id
    assert (await get_contact(database_session, first, contact.id)).id == contact.id
    with pytest.raises(EntityNotFoundError):
        await get_company(database_session, second, company.id)
    with pytest.raises(EntityNotFoundError):
        await get_contact(database_session, second, contact.id)

    second_companies = await list_companies(
        database_session,
        second,
        search=None,
        include_archived=False,
        sort=CompanySort.NAME,
        direction=CompanySortDirection.ASC,
        limit=50,
        offset=0,
    )
    assert second_companies.total == 0


async def test_contact_cannot_reference_a_company_from_another_workspace(
    database_session: AsyncSession,
) -> None:
    first = await _create_context(database_session, "First Relationship")
    second = await _create_context(database_session, "Second Relationship")
    foreign_company = await create_company(
        database_session,
        second,
        name="Foreign Company",
        website=None,
        industry=None,
    )

    with pytest.raises(RelatedEntityNotFoundError):
        await create_contact(
            database_session,
            first,
            company_id=foreign_company.id,
            first_name="Cross",
            last_name="Workspace",
            email=None,
            phone=None,
            job_title=None,
        )

    with pytest.raises(IntegrityError):
        async with database_session.begin_nested():
            database_session.add(
                Contact(
                    workspace_id=first.workspace_id,
                    company_id=foreign_company.id,
                    first_name="Database",
                    last_name="Boundary",
                )
            )
            await database_session.flush()


async def test_optimistic_locking_rejects_stale_updates(
    database_session: AsyncSession,
) -> None:
    context = await _create_context(database_session, "Version User")
    company = await create_company(
        database_session,
        context,
        name="Version One",
        website=None,
        industry=None,
    )
    updated = await update_company(
        database_session,
        context,
        company.id,
        expected_version=1,
        changes={"name": "Version Two"},
    )

    assert updated.version == 2
    with pytest.raises(VersionConflictError):
        await update_company(
            database_session,
            context,
            company.id,
            expected_version=1,
            changes={"name": "Stale Write"},
        )


async def test_viewer_cannot_create_company_or_contact(database_session: AsyncSession) -> None:
    writable = await _create_context(database_session, "Read Only User")
    read_only = replace(writable, role=WorkspaceRole.VIEWER)

    with pytest.raises(WorkspaceWriteForbiddenError):
        await create_company(
            database_session,
            read_only,
            name="Forbidden Company",
            website=None,
            industry=None,
        )
    with pytest.raises(WorkspaceWriteForbiddenError):
        await create_contact(
            database_session,
            read_only,
            company_id=None,
            first_name="Forbidden",
            last_name="Contact",
            email=None,
            phone=None,
            job_title=None,
        )


async def test_contact_filtering_and_update(database_session: AsyncSession) -> None:
    context = await _create_context(database_session, "Filter User")
    company = await create_company(
        database_session,
        context,
        name="Searchable Company",
        website=None,
        industry="Research",
    )
    contact = await create_contact(
        database_session,
        context,
        company_id=company.id,
        first_name="Grace",
        last_name="Hopper",
        email="grace@example.com",
        phone=None,
        job_title="Engineer",
    )

    page = await list_contacts(
        database_session,
        context,
        search="grace@example",
        company_id=company.id,
        include_archived=False,
        sort=ContactSort.NAME,
        direction=SortDirection.ASC,
        limit=10,
        offset=0,
    )
    assert page.total == 1
    assert page.items[0].id == contact.id

    updated = await update_contact(
        database_session,
        context,
        contact.id,
        expected_version=1,
        changes={"job_title": "Rear Admiral", "company_id": None},
    )
    assert updated.version == 2
    assert updated.company_id is None
    assert updated.job_title == "Rear Admiral"


async def test_contacts_and_companies_api_flow(database_session: AsyncSession) -> None:
    settings = Settings(
        _env_file=None,
        registration_enabled=True,
        secret_key="crm-api-integration-secret",
    )

    async def override_session() -> AsyncSession:
        return database_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: settings
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            email = f"crm-api-{uuid4()}@example.com"
            assert (
                await client.post(
                    "/api/v1/auth/register",
                    json={
                        "email": email,
                        "display_name": "CRM API User",
                        "password": "a-strong-development-password",
                    },
                )
            ).status_code == 201
            assert (
                await client.post(
                    "/api/v1/auth/login",
                    json={"email": email, "password": "a-strong-development-password"},
                )
            ).status_code == 200
            workspace_id = (await client.get("/api/v1/workspaces")).json()[0]["id"]
            headers = {"X-Workspace-ID": workspace_id}

            company_response = await client.post(
                "/api/v1/companies",
                headers=headers,
                json={"name": "API Company", "industry": "Technology"},
            )
            assert company_response.status_code == 201
            assert company_response.headers["etag"] == '"1"'
            company_id = company_response.json()["id"]

            contact_response = await client.post(
                "/api/v1/contacts",
                headers=headers,
                json={
                    "company_id": company_id,
                    "first_name": "API",
                    "last_name": "Contact",
                    "email": "api.contact@example.com",
                },
            )
            assert contact_response.status_code == 201
            contact_id = contact_response.json()["id"]

            contact_page = await client.get(
                "/api/v1/contacts?search=api.contact",
                headers=headers,
            )
            assert contact_page.status_code == 200
            assert contact_page.json()["total"] == 1

            update_response = await client.patch(
                f"/api/v1/contacts/{contact_id}",
                headers=headers,
                json={"expected_version": 1, "job_title": "Updated Role"},
            )
            assert update_response.status_code == 200
            assert update_response.json()["version"] == 2

            stale_response = await client.patch(
                f"/api/v1/contacts/{contact_id}",
                headers=headers,
                json={"expected_version": 1, "job_title": "Stale Role"},
            )
            assert stale_response.status_code == 409

            archive_response = await client.delete(
                f"/api/v1/contacts/{contact_id}?expected_version=2",
                headers=headers,
            )
            assert archive_response.status_code == 200
            assert archive_response.json()["status"] == "archived"
            assert (await client.get("/api/v1/contacts", headers=headers)).json()["total"] == 0
            archived_page = await client.get(
                "/api/v1/contacts?include_archived=true", headers=headers
            )
            assert archived_page.json()["total"] == 1

            company_archive = await client.delete(
                f"/api/v1/companies/{company_id}?expected_version=1",
                headers=headers,
            )
            assert company_archive.status_code == 200
            assert company_archive.json()["status"] == "archived"
            assert (await client.get("/api/v1/companies", headers=headers)).json()["total"] == 0
    finally:
        app.dependency_overrides.clear()
