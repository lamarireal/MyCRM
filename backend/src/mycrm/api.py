from fastapi import APIRouter

from mycrm.modules.health.api import router as health_router
from mycrm.modules.identity.api import router as identity_router
from mycrm.modules.workspaces.api import router as workspaces_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(identity_router)
api_router.include_router(workspaces_router)
