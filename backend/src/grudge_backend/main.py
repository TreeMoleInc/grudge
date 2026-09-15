from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from grudge_backend.config import settings
from grudge_backend.db import engine
from grudge_backend.routers import (
    auth,
    automata,
    folders,
    friends,
    internal,
    matchmaking,
    notifications,
    sim_rooms,
    stats,
    tournaments,
    versions,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


app = FastAPI(title="Grudge API", lifespan=lifespan)

# Signs the short-lived OAuth state/PKCE cookie Authlib needs between the login
# redirect and the callback - distinct from the long-lived login-session cookie,
# which is an opaque random token hashed into the `sessions` table (auth/session.py),
# never a signed/decodable value. https_only mirrors settings.cookie_secure so this
# cookie gets the same Secure-flag treatment as the login session cookie - False in
# dev (plain http://localhost), True wherever the app is actually served over https.
#
# max_age=600 (10 minutes), added 2026-09-04: Starlette's own default is 14 days,
# which is wildly longer than this cookie is ever functionally read for - the app
# only ever consults it between the /auth/{provider}/login redirect and the
# matching /callback a few seconds later, never again after that. A privacy-policy
# review flagged the mismatch between that 14-day browser-side expiry and the
# policy's own "temporary, only during sign-in" description - this is the fix on
# the code side; 10 minutes is generous headroom for a slow redirect (Google's own
# 2FA prompt, a slow network) while being unambiguously short-lived.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.oauth_state_secret,
    https_only=settings.cookie_secure,
    max_age=600,
)

# allow_credentials is mandatory here - without it the browser won't attach/accept
# the httpOnly session cookie on cross-origin fetch calls from the Vite dev server
# (a different port = a different origin, even on localhost).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_base_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(folders.router)
app.include_router(automata.router)
app.include_router(versions.router)
app.include_router(matchmaking.router)
app.include_router(sim_rooms.router)
app.include_router(tournaments.router)
app.include_router(tournaments.me_router)
app.include_router(friends.router)
app.include_router(internal.router)
app.include_router(stats.router)
app.include_router(notifications.router)
