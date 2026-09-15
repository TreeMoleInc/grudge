from __future__ import annotations

from fastapi import Depends, Request, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.auth.session import get_user_for_token
from grudge_backend.config import settings
from grudge_backend.db import get_db
from grudge_backend.exceptions import unauthorized
from grudge_backend.models.user import User


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise unauthorized()
    user = await get_user_for_token(db, raw_token=raw_token)
    if user is None:
        raise unauthorized()
    return user


async def get_ws_user(websocket: WebSocket, db: AsyncSession) -> User | None:
    """WebSocket routes can't use a normal FastAPI Depends() for auth the way
    HTTP routes do (there's no response to attach a 401 to before the
    handshake completes) - callers should close with code 4401 if this
    returns None. Reuses the same cookie-hash-lookup as get_current_user.
    """
    raw_token = websocket.cookies.get(settings.session_cookie_name)
    if not raw_token:
        return None
    return await get_user_for_token(db, raw_token=raw_token)
