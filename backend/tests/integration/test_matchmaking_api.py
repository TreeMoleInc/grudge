"""Matchmaking room-fill via the real HTTP join endpoint - the pure
window/spread math is unit-tested separately (tests/unit/test_matchmaking.py).
This proves the wiring: ownership checks, room creation/reuse, the 4th join
triggering a real Tournament+Job, and the ranked window actually keeping
far-apart players separate at join time.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from grudge_backend.models.automaton import Automaton
from grudge_backend.models.job import Job
from grudge_backend.models.tournament import Tournament
from grudge_backend.models.waiting_room import MatchmakingQueueEntry
from tests.conftest import make_player

pytestmark = pytest.mark.integration

_COOPERATE_CODE = "def decide(history):\n    return COOPERATE\n"


_BROKEN_CODE = "def decide(history):\n    raise ValueError('boom')\n"


async def _create_automaton(player_client, *, code: str = _COOPERATE_CODE) -> str:
    resp = await player_client.post("/automata", json={"name": "Bot", "code": code})
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_unranked_room_fills_at_four_and_enqueues_job(client, db_session):
    players = []
    for i in range(4):
        p, _ = await make_player(db_session, username=f"unranked_{i}")
        automaton_id = await _create_automaton(p)
        players.append((p, automaton_id))

    tournament_id = None
    for i, (p, automaton_id) in enumerate(players):
        resp = await p.post("/matchmaking/unranked/join", json={"automaton_id": automaton_id})
        assert resp.status_code == 201
        body = resp.json()
        if i < 3:
            assert body["tournament_id"] is None
        else:
            assert body["tournament_id"] is not None
            tournament_id = body["tournament_id"]

    assert tournament_id is not None

    result = await db_session.execute(select(Tournament).where(Tournament.id == tournament_id))
    tournament = result.scalar_one()
    assert tournament.type == "unranked"
    assert len(tournament.entrants) == 4

    jobs_result = await db_session.execute(select(Job))
    jobs = jobs_result.scalars().all()
    assert any(j.payload.get("tournament_id") == tournament_id for j in jobs)


async def test_join_response_reports_accurate_member_count_for_a_lone_joiner(client, db_session):
    """Regression test: member_count used to come from the WS-connection
    registry, which is always 0 for a lone joiner (their own socket hasn't
    connected yet at the moment this HTTP response is built) - the frontend
    then had nothing to show and got stuck rendering "Joining…" forever,
    since no second player ever arrived to trigger a fresh broadcast. It must
    be the real DB-backed room membership count instead.
    """
    solo, _ = await make_player(db_session, username="lone_joiner")
    bot = await _create_automaton(solo)

    resp = await solo.post("/matchmaking/unranked/join", json={"automaton_id": bot})
    assert resp.status_code == 201
    body = resp.json()
    assert body["member_count"] == 1
    assert body["capacity"] == 4


async def test_ranked_matchmaking_keeps_far_apart_players_in_separate_rooms(client, db_session):
    a, _ = await make_player(db_session, username="ranked_far_a", rating=1000)
    b, _ = await make_player(db_session, username="ranked_far_b", rating=1300)
    a_bot = await _create_automaton(a)
    b_bot = await _create_automaton(b)

    resp_a = await a.post("/matchmaking/ranked/join", json={"automaton_id": a_bot})
    resp_b = await b.post("/matchmaking/ranked/join", json={"automaton_id": b_bot})

    # 300 apart, both fresh joins (radius 100) - doesn't fit, so separate rooms.
    assert resp_a.json()["room_id"] != resp_b.json()["room_id"]


async def test_ranked_matchmaking_groups_compatible_players_together(client, db_session):
    a, _ = await make_player(db_session, username="ranked_close_a", rating=1000)
    b, _ = await make_player(db_session, username="ranked_close_b", rating=1050)
    a_bot = await _create_automaton(a)
    b_bot = await _create_automaton(b)

    resp_a = await a.post("/matchmaking/ranked/join", json={"automaton_id": a_bot})
    resp_b = await b.post("/matchmaking/ranked/join", json={"automaton_id": b_bot})

    assert resp_a.json()["room_id"] == resp_b.json()["room_id"]


async def test_leave_queue_then_rejoin_succeeds_immediately(client, db_session):
    a, _ = await make_player(db_session, username="leave_then_rejoin")
    bot = await _create_automaton(a)

    join_resp = await a.post("/matchmaking/unranked/join", json={"automaton_id": bot})
    entry_id = join_resp.json()["entry_id"]

    leave_resp = await a.delete(f"/matchmaking/queue/{entry_id}")
    assert leave_resp.status_code == 204

    # Without the explicit leave, this would 400 (AlreadyQueuedError) for up to
    # HEARTBEAT_STALE_SECONDS behind the stale-heartbeat sweep.
    rejoin_resp = await a.post("/matchmaking/unranked/join", json={"automaton_id": bot})
    assert rejoin_resp.status_code == 201


async def test_leave_queue_twice_returns_404(client, db_session):
    a, _ = await make_player(db_session, username="leave_twice")
    bot = await _create_automaton(a)
    entry_id = (await a.post("/matchmaking/unranked/join", json={"automaton_id": bot})).json()[
        "entry_id"
    ]

    assert (await a.delete(f"/matchmaking/queue/{entry_id}")).status_code == 204
    assert (await a.delete(f"/matchmaking/queue/{entry_id}")).status_code == 404


async def test_leave_someone_elses_queue_entry_returns_404(client, db_session):
    a, _ = await make_player(db_session, username="leave_owner")
    b, _ = await make_player(db_session, username="leave_intruder")
    bot = await _create_automaton(a)
    entry_id = (await a.post("/matchmaking/unranked/join", json={"automaton_id": bot})).json()[
        "entry_id"
    ]

    resp = await b.delete(f"/matchmaking/queue/{entry_id}")
    assert resp.status_code == 404


async def test_already_queued_returns_400(client, db_session):
    a, _ = await make_player(db_session, username="already_queued")
    bot1 = await _create_automaton(a)
    resp1 = await a.post("/automata", json={"name": "Bot2", "code": _COOPERATE_CODE})
    bot2 = resp1.json()["id"]

    resp = await a.post("/matchmaking/unranked/join", json={"automaton_id": bot1})
    assert resp.status_code == 201

    resp = await a.post("/matchmaking/unranked/join", json={"automaton_id": bot2})
    assert resp.status_code == 400


async def test_join_nonexistent_automaton_returns_404(client, db_session):
    a, _ = await make_player(db_session, username="nonexistent_automaton")
    resp = await a.post(
        "/matchmaking/unranked/join",
        json={"automaton_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


async def test_unknown_queue_type_returns_404(client, db_session):
    a, _ = await make_player(db_session, username="unknown_queue_type")
    bot = await _create_automaton(a)
    resp = await a.post("/matchmaking/bogus/join", json={"automaton_id": bot})
    assert resp.status_code == 404


async def test_broken_automaton_fails_preflight_and_cannot_join(client, db_session):
    a, _ = await make_player(db_session, username="preflight_broken")
    bot = await _create_automaton(a, code=_BROKEN_CODE)

    resp = await a.post("/matchmaking/unranked/join", json={"automaton_id": bot})

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail  # a real, non-generic reason from PreflightResult, not empty
    assert detail != "You already have an active queue entry."

    # No side effects: the failed pre-flight check runs before any row is
    # written, so nothing was queued for THIS automaton (scoped, not a
    # whole-table check, since other tests' rows share this session).
    entries_result = await db_session.execute(
        select(MatchmakingQueueEntry).where(MatchmakingQueueEntry.automaton_id == uuid.UUID(bot))
    )
    assert entries_result.scalars().all() == []


async def test_automaton_with_no_active_version_cannot_join(client, db_session):
    a, _ = await make_player(db_session, username="preflight_no_version")
    bot_id = await _create_automaton(a)

    # Not reachable through the real API today (creation always sets an
    # active version, and CLAUDE.md forbids deleting an automaton's only
    # version) - this defensive branch in services/matchmaking.py:join_queue
    # is still worth covering directly, in case that invariant ever changes.
    automaton = await db_session.get(Automaton, uuid.UUID(bot_id))
    automaton.active_version_id = None
    await db_session.commit()

    resp = await a.post("/matchmaking/unranked/join", json={"automaton_id": bot_id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "This automaton has no active version to enter with."
