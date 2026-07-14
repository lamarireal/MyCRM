from fastapi import APIRouter

from mycrm.modules.health.api import router as health_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
