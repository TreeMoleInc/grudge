"""Session row create/lookup/destroy. Sessions are opaque random tokens hashed
with SHA-256 before storage - the raw token is only ever available at creation
time (to set as the cookie value) and is never persisted anywhere.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.config import settings
from grudge_backend.models.session import Session as SessionModel
from grudge_backend.models.user import User

# Only bump last_seen_at if it's gone stale by at least this long - avoids a
# write on every single authenticated request (this dependency runs on nearly
# every HTTP/WS call) when the value is already fresh enough for the home
# page's "players online" approximation (services/stats.py's ONLINE_WINDOW_SECONDS)
# to not care about sub-30s precision.
_LAST_SEEN_UPDATE_THROTTLE_SECONDS = 30


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def create_session(db: AsyncSession, *, user_id: uuid.UUID) -> str:
    raw_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    db.add(
        SessionModel(
            user_id=user_id,
            token_hash=_hash_token(raw_token),
            expires_at=now + timedelta(days=settings.session_ttl_days),
            last_seen_at=now,
        )
    )
    await db.flush()
    return raw_token


async def get_user_for_token(db: AsyncSession, *, raw_token: str) -> User | None:
    token_hash = _hash_token(raw_token)
    now = datetime.now(UTC)
    result = await db.execute(
        select(User)
        .join(SessionModel, SessionModel.user_id == User.id)
        .where(SessionModel.token_hash == token_hash, SessionModel.expires_at > now)
    )
    user = result.scalar_one_or_none()
    if user is not None:
        # Throttled in the WHERE clause itself (not a separate read-then-write)
        # so an already-fresh row costs a 0-row UPDATE instead of a round trip
        # plus a write - this runs on nearly every authenticated request.
        # Committed immediately (rather than left for the route handler, which
        # may never call commit() at all on a pure GET) since expire_on_commit
        # is off, so `user`'s already-loaded attributes stay safely usable by
        # the caller afterward.
        stale_before = now - timedelta(seconds=_LAST_SEEN_UPDATE_THROTTLE_SECONDS)
        update_result = await db.execute(
            update(SessionModel)
            .where(SessionModel.token_hash == token_hash, SessionModel.last_seen_at < stale_before)
            .values(last_seen_at=now)
        )
        if update_result.rowcount:
            await db.commit()
    return user


async def destroy_session(db: AsyncSession, *, raw_token: str) -> None:
    await db.execute(delete(SessionModel).where(SessionModel.token_hash == _hash_token(raw_token)))
    await db.flush()


async def sweep_expired_sessions(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Deletes session rows whose expires_at has passed. Without this, an
    expired session just silently stops being usable (get_user_for_token's
    WHERE clause already excludes it) but the row itself sat in the table
    forever - every login that doesn't end in an explicit logout (closed tab,
    crashed browser, just letting the 30-day cookie lapse) left a permanent
    dead row. Returns the number of rows deleted, for logging.
    """
    now = now or datetime.now(UTC)
    result = await db.execute(delete(SessionModel).where(SessionModel.expires_at <= now))
    await db.flush()
    return result.rowcount
