from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mycrm.core.config import Settings
from mycrm.modules.identity.models import AuthSession, User, UserStatus
from mycrm.modules.identity.security import (
    create_session_token,
    hash_password,
    hash_session_token,
    verify_password_or_dummy,
)
from mycrm.modules.workspaces.domain import WorkspaceKind, WorkspaceRole, WorkspaceStatus
from mycrm.modules.workspaces.models import Workspace, WorkspaceMembership


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InvalidSessionError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CreatedSession:
    token: str
    user: User


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    display_name: str,
    password: str,
) -> User:
    normalized_email = email.strip().lower()
    existing = await session.scalar(
        select(User.id).where(func.lower(User.email) == normalized_email)
    )
    if existing is not None:
        raise EmailAlreadyRegisteredError

    user = User(
        email=normalized_email,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        status=UserStatus.ACTIVE,
    )
    try:
        async with session.begin_nested():
            session.add(user)
            await session.flush()
    except IntegrityError as exc:
        raise EmailAlreadyRegisteredError from exc

    workspace = Workspace(
        name=f"{user.display_name}'s workspace",
        slug=f"personal-{user.id.hex[:12]}",
        kind=WorkspaceKind.PRIVATE,
        status=WorkspaceStatus.ACTIVE,
    )
    session.add(workspace)
    await session.flush()
    session.add(
        WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user.id,
            role=WorkspaceRole.OWNER,
        )
    )
    return user


async def authenticate_user(
    session: AsyncSession,
    settings: Settings,
    *,
    email: str,
    password: str,
) -> CreatedSession:
    normalized_email = email.strip().lower()
    user = await session.scalar(select(User).where(func.lower(User.email) == normalized_email))
    password_is_valid = verify_password_or_dummy(
        password, user.password_hash if user is not None else None
    )
    if (
        user is None
        or user.status != UserStatus.ACTIVE
        or user.password_hash is None
        or not password_is_valid
    ):
        raise InvalidCredentialsError

    token = create_session_token()
    now = datetime.now(UTC)
    session.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_session_token(token, settings.secret_key.get_secret_value()),
            expires_at=now + timedelta(days=settings.session_ttl_days),
            last_seen_at=now,
        )
    )
    return CreatedSession(token=token, user=user)


async def resolve_user_session(
    session: AsyncSession, settings: Settings, token: str | None
) -> tuple[User, AuthSession]:
    if not token:
        raise InvalidSessionError

    token_digest = hash_session_token(token, settings.secret_key.get_secret_value())
    result = await session.execute(
        select(User, AuthSession)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            AuthSession.token_hash == token_digest,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
            User.status == UserStatus.ACTIVE,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise InvalidSessionError

    user, auth_session = row
    auth_session.last_seen_at = datetime.now(UTC)
    return user, auth_session


async def revoke_session(session: AsyncSession, settings: Settings, token: str | None) -> None:
    if not token:
        return
    token_digest = hash_session_token(token, settings.secret_key.get_secret_value())
    auth_session = await session.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_digest,
            AuthSession.revoked_at.is_(None),
        )
    )
    if auth_session is not None:
        auth_session.revoked_at = datetime.now(UTC)
