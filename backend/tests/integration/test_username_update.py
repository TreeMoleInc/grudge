"""PATCH /me - player-chosen usernames (CLAUDE.md S2, migration 0011).
Format validation (schemas/user.py's USERNAME_PATTERN) is exercised here
through the real endpoint rather than as a separate schema unit test, since
FastAPI/Pydantic's own 422 handling is part of what's being verified.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_update_username_succeeds_and_clears_default_flag(auth_client, user):
    assert user.username_is_default is True

    resp = await auth_client.patch("/me", json={"username": "newname"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "newname"
    assert body["username_is_default"] is False


async def test_update_username_rejects_case_insensitive_collision(
    auth_client, other_user, db_session
):
    other_user.username = "TakenName"
    await db_session.flush()

    resp = await auth_client.patch("/me", json={"username": "takenname"})
    assert resp.status_code == 409


async def test_update_username_allows_recasing_your_own_name(auth_client, user, db_session):
    user.username = "Alice"
    await db_session.flush()

    resp = await auth_client.patch("/me", json={"username": "alice"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"


@pytest.mark.parametrize(
    "bad_username",
    [
        "ab",  # too short
        "a" * 21,  # too long
        "has space",
        "has.dot",
        "has@symbol",
        "",
    ],
)
async def test_update_username_rejects_bad_format(auth_client, bad_username):
    resp = await auth_client.patch("/me", json={"username": bad_username})
    assert resp.status_code == 422


async def test_update_username_requires_auth(client):
    resp = await client.patch("/me", json={"username": "someone"})
    assert resp.status_code == 401


async def test_username_lookup_for_friend_requests_is_case_insensitive(
    auth_client, other_user, db_session
):
    other_user.username = "CoolPlayer"
    await db_session.flush()

    resp = await auth_client.post("/friends/requests", json={"username": "coolplayer"})
    assert resp.status_code == 201
    assert resp.json()["to_user_id"] == str(other_user.id)
