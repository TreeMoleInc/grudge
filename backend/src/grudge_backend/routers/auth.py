from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.auth.dependencies import get_current_user
from grudge_backend.auth.oauth import oauth
from grudge_backend.auth.providers import fetch_google_user
from grudge_backend.auth.session import create_session, destroy_session
from grudge_backend.config import settings
from grudge_backend.db import get_db
from grudge_backend.exceptions import conflict
from grudge_backend.models.user import AuthIdentity, User
from grudge_backend.schemas.auth import ProviderUserInfo
from grudge_backend.schemas.user import UserRead
from grudge_backend.services import account as account_service

router = APIRouter(tags=["auth"])


@router.get("/auth/google/login")
async def google_login(request: Request):
    redirect_uri = f"{settings.backend_base_url}/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/google/callback")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    info = await fetch_google_user(token)
    return await _complete_login(db, info)


async def _complete_login(db: AsyncSession, info: ProviderUserInfo) -> RedirectResponse:
    user = await _login_or_create_user(db, info)
    raw_token = await create_session(db, user_id=user.id)
    await db.commit()

    response = RedirectResponse(url=settings.frontend_base_url)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_ttl_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return response


async def _login_or_create_user(db: AsyncSession, info: ProviderUserInfo) -> User:
    """Looks up by (provider, provider_user_id) - the actual login key. Provider-
    agnostic on purpose even though Google is the only provider registered today
    (GitHub was dropped 2026-09-04, CLAUDE.md S2) - adding a future provider (e.g.
    Discord) needs no change here, just a new oauth.register() + fetch_*_user +
    route trio.
    """
    result = await db.execute(
        select(AuthIdentity).where(
            AuthIdentity.provider == info.provider,
            AuthIdentity.provider_user_id == info.provider_user_id,
        )
    )
    identity = result.scalar_one_or_none()
    if identity is not None:
        user = await db.get(User, identity.user_id)
        assert user is not None  # FK guarantees this
        return user

    username = await _unique_username(db, info.username)
    user = User(username=username, email=info.email, avatar_url=info.avatar_url)
    db.add(user)
    await db.flush()

    db.add(
        AuthIdentity(
            user_id=user.id,
            provider=info.provider,
            provider_user_id=info.provider_user_id,
            provider_email=info.email,
        )
    )
    await db.flush()
    return user


async def _unique_username(db: AsyncSession, base: str) -> str:
    candidate = base or "user"
    suffix = 0
    while True:
        result = await db.execute(select(User.id).where(User.username == candidate))
        if result.scalar_one_or_none() is None:
            return candidate
        suffix += 1
        candidate = f"{base}{suffix}"


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        await destroy_session(db, raw_token=raw_token)
        await db.commit()
    response = Response(status_code=204)
    response.delete_cookie(settings.session_cookie_name)
    return response


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.delete("/me", status_code=204)
async def delete_my_account(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Response:
    """Irreversible. Deletes the account (email/avatar/provider identities,
    automata, friendships, sessions - see services/account.py for the full
    cascade) but keeps tournament/match history, with the player's name
    replaced by an anonymized label everywhere it appears in that history.
    """
    try:
        await account_service.delete_account(db, user=current_user)
    except account_service.AccountCurrentlyActiveError as exc:
        # No rollback needed here (unlike e.g. matchmaking's AlreadyQueuedError
        # path) - delete_account's active-state check runs before any write,
        # so nothing has touched the session yet when this raises.
        raise conflict(str(exc)) from exc

    await db.commit()
    response = Response(status_code=204)
    response.delete_cookie(settings.session_cookie_name)
    return response
