"""GET /me/active-state - powers the Settings page's self-service "what's
blocking my account deletion" panel (services/account.py's get_active_state).
Reuses the exact same setup patterns as test_account_deletion_api.py's
blocking-condition tests, since this endpoint has to report the identical
three conditions DELETE /me itself checks.
"""

from __future__ import annotations

import pytest

from tests.conftest import make_player

pytestmark = pytest.mark.integration

_COOPERATE_CODE = "def decide(history):\n    return COOPERATE\n"


async def test_active_state_is_empty_for_an_idle_account(client, db_session):
    player, _user = await make_player(db_session, username="idle_player")
    resp = await player.get("/me/active-state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["queue_entry"] is None
    assert body["sim_rooms"] == []
    assert body["tournament_ids"] == []


async def test_active_state_reports_a_waiting_queue_entry(client, db_session):
    player, _user = await make_player(db_session, username="queued_player")
    bot_resp = await player.post("/automata", json={"name": "Bot", "code": _COOPERATE_CODE})
    await player.post("/matchmaking/unranked/join", json={"automaton_id": bot_resp.json()["id"]})

    resp = await player.get("/me/active-state")
    body = resp.json()
    assert body["queue_entry"]["queue_type"] == "unranked"


async def test_active_state_reports_a_room_the_player_entered(client, db_session):
    player, _user = await make_player(db_session, username="entered_player")
    bot_resp = await player.post("/automata", json={"name": "Bot", "code": _COOPERATE_CODE})
    room_resp = await player.post("/sim-rooms")
    await player.post(
        "/sim-rooms/join",
        json={"code": room_resp.json()["invite_code"], "automaton_id": bot_resp.json()["id"]},
    )

    resp = await player.get("/me/active-state")
    body = resp.json()
    assert len(body["sim_rooms"]) == 1
    assert body["sim_rooms"][0]["id"] == room_resp.json()["id"]
    assert body["sim_rooms"][0]["is_owner"] is True


async def test_active_state_reports_a_room_owned_with_no_entry_of_your_own(client, db_session):
    owner, _owner_user = await make_player(db_session, username="owns_empty_room")
    other, _ = await make_player(db_session, username="other_in_owned_room")
    room_resp = await owner.post("/sim-rooms")
    other_bot = await other.post("/automata", json={"name": "Bot", "code": _COOPERATE_CODE})
    await other.post(
        "/sim-rooms/join",
        json={"code": room_resp.json()["invite_code"], "automaton_id": other_bot.json()["id"]},
    )

    resp = await owner.get("/me/active-state")
    body = resp.json()
    assert len(body["sim_rooms"]) == 1
    assert body["sim_rooms"][0]["is_owner"] is True


async def test_active_state_deduplicates_a_room_you_own_and_have_entered(client, db_session):
    owner, _owner_user = await make_player(db_session, username="owns_and_entered")
    bot_resp = await owner.post("/automata", json={"name": "Bot", "code": _COOPERATE_CODE})
    room_resp = await owner.post("/sim-rooms")
    await owner.post(
        "/sim-rooms/join",
        json={"code": room_resp.json()["invite_code"], "automaton_id": bot_resp.json()["id"]},
    )

    resp = await owner.get("/me/active-state")
    body = resp.json()
    # One row, not two, for the same room - the owner is also its sole entrant.
    assert len(body["sim_rooms"]) == 1
    assert body["sim_rooms"][0]["is_owner"] is True


async def test_leaving_the_reported_room_clears_active_state_and_unblocks_deletion(
    client, db_session
):
    owner, owner_user = await make_player(db_session, username="leaves_owned_room")
    room_resp = await owner.post("/sim-rooms")
    room_id = room_resp.json()["id"]

    state_before = await owner.get("/me/active-state")
    assert len(state_before.json()["sim_rooms"]) == 1

    await owner.post(f"/sim-rooms/{room_id}/leave")

    state_after = await owner.get("/me/active-state")
    assert state_after.json()["sim_rooms"] == []

    # Confirms the guarantee in get_active_state's docstring: clearing
    # everything this endpoint reports is enough to unblock deletion.
    delete_resp = await owner.delete("/me")
    assert delete_resp.status_code == 204


async def test_active_state_requires_auth(client):
    resp = await client.get("/me/active-state")
    assert resp.status_code == 401
