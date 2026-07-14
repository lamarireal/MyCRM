from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.config import Settings, get_settings
from mycrm.core.database import get_session

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    service: str
    version: str


@router.get("/live", response_model=HealthResponse)
async def liveness(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name, version=settings.app_version)


@router.get("/ready", response_model=HealthResponse)
async def readiness(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HealthResponse:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc

    return HealthResponse(status="ok", service=settings.app_name, version=settings.app_version)
