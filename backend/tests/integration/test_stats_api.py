"""GET /stats/live - the home page's approximate "players online" / "players
in a match or queue" counters. Deliberately unauthenticated (logged-out
visitors see it too) and deliberately approximate (derived from
sessions.last_seen_at, not a realtime presence channel) - see
services/stats.py's module docstring.

These assert on the CHANGE in each count around an action, not an absolute
value - `db_session`'s savepoint-per-test rollback only undoes what THIS test
adds, not pre-existing rows in the shared dev database (real sessions/rooms/
tournaments from manual testing elsewhere in this same DB) - so an absolute
"online_count == 1" assertion is only reliably true in a database nobody else
has ever touched, which `grudge_dev` isn't. A before/after delta is the
correct way to test a global aggregate against a database that's shared with
whatever else has been run against it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from grudge_backend.models.session import Session as SessionModel
from grudge_backend.models.tournament import Tournament
from grudge_backend.models.waiting_room import MatchmakingQueueEntry
from tests.conftest import make_player

pytestmark = pytest.mark.integration

_COOPERATE_CODE = "def decide(history):\n    return COOPERATE\n"


async def _live(client) -> dict:
    resp = await client.get("/stats/live")
    assert resp.status_code == 200
    return resp.json()


async def test_endpoint_requires_no_authentication(client, db_session):
    # No cookie set on `client` at all in this test - must still succeed.
    resp = await client.get("/stats/live")
    assert resp.status_code == 200
    assert set(resp.json().keys()) == {"online_count", "in_activity_count"}


async def test_a_logged_in_player_increases_online_count_by_one(client, db_session):
    before = await _live(client)
    await make_player(db_session, username="online_alice")
    after = await _live(client)
    assert after["online_count"] == before["online_count"] + 1


async def test_two_sessions_for_the_same_user_still_count_once(client, db_session):
    from grudge_backend.auth.session import create_session

    before = await _live(client)
    _p, user = await make_player(db_session, username="two_sessions")
    await create_session(db_session, user_id=user.id)  # a second device/session
    await db_session.flush()
    after = await _live(client)
    assert after["online_count"] == before["online_count"] + 1


async def test_a_stale_session_does_not_count_as_online(client, db_session):
    before = await _live(client)
    _p, user = await make_player(db_session, username="stale_bob")

    stale_time = datetime.now(UTC) - timedelta(seconds=999)
    result = await db_session.execute(select(SessionModel).where(SessionModel.user_id == user.id))
    for session_row in result.scalars().all():
        session_row.last_seen_at = stale_time
    await db_session.flush()

    after = await _live(client)
    assert after["online_count"] == before["online_count"]


async def test_a_waiting_matchmaking_entry_counts_toward_in_activity(client, db_session):
    before = await _live(client)
    player, _user = await make_player(db_session, username="queued_carol")
    resp = await player.post("/automata", json={"name": "Bot", "code": _COOPERATE_CODE})
    automaton_id = resp.json()["id"]
    join_resp = await player.post("/matchmaking/unranked/join", json={"automaton_id": automaton_id})
    assert join_resp.status_code == 201

    after = await _live(client)
    assert after["in_activity_count"] == before["in_activity_count"] + 1


async def test_a_matched_entry_no_longer_counts(client, db_session):
    """Once matched, an entry's status flips away from "waiting" - it should
    stop counting here (it'll show up via the running-tournament count
    instead, once/if the room actually fills - a lone joiner never reaches
    that state, so this specifically checks the "waiting" cutoff by manually
    flipping the status a real join would eventually reach on its own).
    """
    player, user = await make_player(db_session, username="solo_dave")
    resp = await player.post("/automata", json={"name": "Bot", "code": _COOPERATE_CODE})
    automaton_id = resp.json()["id"]
    await player.post("/matchmaking/unranked/join", json={"automaton_id": automaton_id})
    waiting = await _live(client)

    entry_result = await db_session.execute(
        select(MatchmakingQueueEntry).where(MatchmakingQueueEntry.user_id == user.id)
    )
    entry = entry_result.scalar_one()
    entry.status = "evicted"
    await db_session.flush()

    after = await _live(client)
    assert after["in_activity_count"] == waiting["in_activity_count"] - 1


async def test_a_player_in_an_open_sim_room_counts_toward_in_activity(client, db_session):
    before = await _live(client)
    player, _user = await make_player(db_session, username="sim_erin")
    resp = await player.post("/automata", json={"name": "Bot", "code": _COOPERATE_CODE})
    automaton_id = resp.json()["id"]
    room_resp = await player.post("/sim-rooms")
    invite_code = room_resp.json()["invite_code"]
    join_resp = await player.post(
        "/sim-rooms/join", json={"code": invite_code, "automaton_id": automaton_id}
    )
    assert join_resp.status_code == 201

    after = await _live(client)
    assert after["in_activity_count"] == before["in_activity_count"] + 1


async def test_entrants_of_a_running_tournament_count_toward_in_activity(client, db_session):
    before = await _live(client)
    tournament = Tournament(
        type="sim",
        status="running",
        entrants=[
            {"user_id": "00000000-0000-0000-0000-000000000001", "automaton_id": "a"},
            {"user_id": "00000000-0000-0000-0000-000000000002", "automaton_id": "b"},
        ],
    )
    db_session.add(tournament)
    await db_session.flush()

    after = await _live(client)
    assert after["in_activity_count"] == before["in_activity_count"] + 2


async def test_entrants_of_a_completed_tournament_do_not_count(client, db_session):
    before = await _live(client)
    tournament = Tournament(
        type="sim",
        status="completed",
        entrants=[{"user_id": "00000000-0000-0000-0000-000000000001", "automaton_id": "a"}],
    )
    db_session.add(tournament)
    await db_session.flush()

    after = await _live(client)
    assert after["in_activity_count"] == before["in_activity_count"]
