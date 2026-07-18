from fastapi import APIRouter

from mycrm.modules.activities.api import router as activities_router
from mycrm.modules.audit.api import router as audit_router
from mycrm.modules.companies.api import router as companies_router
from mycrm.modules.contacts.api import router as contacts_router
from mycrm.modules.deals.api import router as deals_router
from mycrm.modules.health.api import router as health_router
from mycrm.modules.identity.api import router as identity_router
from mycrm.modules.notes.api import router as notes_router
from mycrm.modules.pipelines.api import router as pipelines_router
from mycrm.modules.tasks.api import router as tasks_router
from mycrm.modules.workspaces.api import router as workspaces_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(companies_router)
api_router.include_router(contacts_router)
api_router.include_router(pipelines_router)
api_router.include_router(deals_router)
api_router.include_router(tasks_router)
api_router.include_router(activities_router)
api_router.include_router(audit_router)
api_router.include_router(notes_router)
api_router.include_router(health_router)
api_router.include_router(identity_router)
api_router.include_router(workspaces_router)
