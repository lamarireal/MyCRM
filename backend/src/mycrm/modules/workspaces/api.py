from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from mycrm.core.config import Settings, get_settings

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoCapabilitiesResponse(BaseModel):
    enabled: bool
    read_only: bool
    synthetic_data_only: bool = True
    external_side_effects_enabled: bool = False


@router.get("/capabilities", response_model=DemoCapabilitiesResponse)
async def demo_capabilities(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DemoCapabilitiesResponse:
    return DemoCapabilitiesResponse(
        enabled=settings.demo_enabled, read_only=settings.demo_read_only
    )
