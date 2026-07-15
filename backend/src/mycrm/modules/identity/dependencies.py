from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.config import Settings, get_settings
from mycrm.core.database import get_session
from mycrm.modules.identity.application import InvalidSessionError, resolve_user_session
from mycrm.modules.identity.models import AuthSession, User


async def get_current_identity(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> tuple[User, AuthSession]:
    token = request.cookies.get(settings.session_cookie_name)
    try:
        return await resolve_user_session(session, settings, token)
    except InvalidSessionError as exc:
        raise HTTPException(status_code=401, detail="Authentication required") from exc


CurrentIdentity = Annotated[tuple[User, AuthSession], Depends(get_current_identity)]


async def get_current_user(identity: CurrentIdentity) -> User:
    return identity[0]


CurrentUser = Annotated[User, Depends(get_current_user)]
