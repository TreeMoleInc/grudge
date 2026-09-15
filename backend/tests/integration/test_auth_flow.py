"""OAuth callback business logic (_login_or_create_user) tested directly against
a real DB, rather than through the full HTTP OAuth dance - the fetch_*_user
provider wrappers are unit-tested separately (tests/unit/test_oauth_providers.py)
without needing real network or Authlib internals.

Known gap, tracked in TODO.md: a deeper end-to-end test exercising the real
/auth/{provider}/login -> callback endpoints with respx-mocked provider HTTP
calls (validating the actual Authlib wiring, not just our own upsert logic)
is not written yet.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from grudge_backend.models.user import AuthIdentity
from grudge_backend.routers.auth import _login_or_create_user
from grudge_backend.schemas.auth import ProviderUserInfo

pytestmark = pytest.mark.integration


async def test_login_or_create_user_creates_new_user_and_identity(db_session):
    info = ProviderUserInfo(
        provider="google",
        provider_user_id="1",
        email="a@example.com",
        username="alice",
        avatar_url=None,
    )
    user = await _login_or_create_user(db_session, info)

    assert user.username == "alice"
    result = await db_session.execute(select(AuthIdentity).where(AuthIdentity.user_id == user.id))
    identity = result.scalar_one()
    assert identity.provider == "google"
    assert identity.provider_user_id == "1"


async def test_login_or_create_user_reuses_existing_identity(db_session):
    info = ProviderUserInfo(
        provider="google",
        provider_user_id="1",
        email="a@example.com",
        username="alice",
        avatar_url=None,
    )
    first = await _login_or_create_user(db_session, info)
    second = await _login_or_create_user(db_session, info)
    assert first.id == second.id


async def test_login_or_create_user_handles_username_collision(db_session):
    info_a = ProviderUserInfo(
        provider="google",
        provider_user_id="1",
        email="a@example.com",
        username="taken",
        avatar_url=None,
    )
    info_b = ProviderUserInfo(
        provider="google",
        provider_user_id="2",
        email="b@example.com",
        username="taken",
        avatar_url=None,
    )

    user_a = await _login_or_create_user(db_session, info_a)
    user_b = await _login_or_create_user(db_session, info_b)

    assert user_a.username == "taken"
    assert user_b.username == "taken1"
    assert user_a.id != user_b.id


async def test_login_or_create_user_stays_provider_agnostic(db_session):
    # _login_or_create_user keys off (provider, provider_user_id) generically -
    # it doesn't hardcode "google" anywhere, so it's still correct if a second
    # provider (e.g. Discord, see CLAUDE.md S2) is ever added back. Exercised
    # here with a hypothetical second provider name even though only "google"
    # is actually registered in auth/oauth.py today.
    info_google = ProviderUserInfo(
        provider="google",
        provider_user_id="1",
        email="same@example.com",
        username="same_person",
        avatar_url=None,
    )
    info_other = ProviderUserInfo(
        provider="discord",
        provider_user_id="2",
        email="same@example.com",
        username="same_person",
        avatar_url=None,
    )

    user_a = await _login_or_create_user(db_session, info_google)
    user_b = await _login_or_create_user(db_session, info_other)
    assert user_a.id != user_b.id


async def test_me_returns_current_user(auth_client, user):
    resp = await auth_client.get("/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(user.id)
    assert body["username"] == user.username
    assert body["rating"] == 1000


async def test_me_without_session_returns_401(client):
    resp = await client.get("/me")
    assert resp.status_code == 401


async def test_logout_clears_session(auth_client):
    resp = await auth_client.post("/auth/logout")
    assert resp.status_code == 204

    resp = await auth_client.get("/me")
    assert resp.status_code == 401
