"""Dev/E2E-only helper: creates (or reuses) a user by username and prints a
fresh raw session token to stdout. Used by frontend/tests/e2e's Playwright
fixtures to log in without a real OAuth round-trip - the browser never touches
this script directly, it just gets the resulting cookie value handed to it via
`context.addCookies(...)`.

No production equivalent exists (and shouldn't - this bypasses auth
entirely), which is exactly why it's a standalone script under scripts/, not
an API endpoint. Run manually or from Playwright's fixtures.ts via
child_process, e.g.:

    python -m grudge_backend.worker  # separately, already running
    python scripts/seed_e2e_user.py my_test_user
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from grudge_backend.auth.session import create_session
from grudge_backend.db import async_session_maker
from grudge_backend.models.user import User


async def main(username: str) -> str:
    async with async_session_maker() as db:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(username=username, rating=1000)
            db.add(user)
            await db.flush()
        token = await create_session(db, user_id=user.id)
        await db.commit()
        return token


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: seed_e2e_user.py <username>", file=sys.stderr)
        sys.exit(1)
    print(asyncio.run(main(sys.argv[1])))
