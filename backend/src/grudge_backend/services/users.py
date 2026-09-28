"""Player-chosen usernames (CLAUDE.md S2). Format is validated at the schema
layer (schemas/user.py's USERNAME_PATTERN) before this module is ever
reached - this module only does the one thing a schema validator can't:
check the name against every *other* account.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.models.user import User


class UsernameTakenError(Exception):
    pass


async def update_username(db: AsyncSession, *, user: User, new_username: str) -> None:
    """Case-insensitive uniqueness check, matching the DB's own
    ux_users_username_lower functional index (migration 0011) - so a
    collision is always caught here first, with a friendly message, rather
    than surfacing as a raw IntegrityError from the index. Excludes the
    caller's own row so re-submitting the same name (or just changing its
    case) is never rejected as "taken by yourself."
    """
    existing = await db.execute(
        select(User.id).where(func.lower(User.username) == new_username.lower(), User.id != user.id)
    )
    if existing.scalar_one_or_none() is not None:
        raise UsernameTakenError("That username is already taken.")

    user.username = new_username
    user.username_is_default = False
    await db.flush()
