"""GET /me/tournaments - the Play page's History tab and the Automata page's
history section both read from this. Builds Tournament rows directly with a
hand-crafted `result` blob (bypassing the real worker/engine, which
test_worker.py already covers) since this endpoint's own logic - the JSONB
containment query plus placement/voided derivation - doesn't depend on the
engine actually having run.
"""

from __future__ import annotations

import uuid

import pytest

from grudge_backend.models.tournament import Tournament
from tests.conftest import make_player

pytestmark = pytest.mark.integration

_COOPERATE_CODE = "def decide(history):\n    return COOPERATE\n"


def _entrant(*, user_id, automaton_id: str, automaton_name: str, username: str) -> dict:
    return {
        "user_id": str(user_id),
        "automaton_id": automaton_id,
        "automaton_version_id": None,
        "code_snapshot": _COOPERATE_CODE,
        "rating_snapshot": 1000,
        "automaton_name": automaton_name,
        "automaton_version_name": "v1",
        "owner_username": username,
    }


async def test_completed_tournament_shows_placement(client, db_session):
    player, user = await make_player(db_session, username="history_completed")
    other_id = str(uuid.uuid4())
    my_automaton_id = str(uuid.uuid4())

    tournament = Tournament(
        type="unranked",
        status="completed",
        entrants=[
            _entrant(
                user_id=user.id,
                automaton_id=my_automaton_id,
                automaton_name="MyBot",
                username=user.username,
            ),
            _entrant(
                user_id=other_id, automaton_id="opp-1", automaton_name="OppBot", username="opponent"
            ),
        ],
        result={
            "standings": [
                {
                    "automaton_id": "opp-1",
                    "total_points": 300,
                    "total_games": 100,
                    "points_per_game": 3.0,
                },
                {
                    "automaton_id": my_automaton_id,
                    "total_points": 200,
                    "total_games": 100,
                    "points_per_game": 2.0,
                },
            ],
            "faulted": [],
        },
    )
    db_session.add(tournament)
    await db_session.flush()
    await db_session.commit()

    resp = await player.get("/me/tournaments")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["automaton_name"] == "MyBot"
    assert row["placement"] == 2  # second in standings
    assert row["voided"] is False


async def test_voided_entrant_shows_no_placement(client, db_session):
    player, user = await make_player(db_session, username="history_voided")
    my_automaton_id = str(uuid.uuid4())

    tournament = Tournament(
        type="unranked",
        status="completed",
        entrants=[
            _entrant(
                user_id=user.id,
                automaton_id=my_automaton_id,
                automaton_name="BrokenBot",
                username=user.username,
            ),
        ],
        result={
            "standings": [],
            "faulted": [{"automaton_id": my_automaton_id, "reason": "crashed"}],
        },
    )
    db_session.add(tournament)
    await db_session.flush()
    await db_session.commit()

    resp = await player.get("/me/tournaments")
    row = resp.json()[0]
    assert row["placement"] is None
    assert row["voided"] is True


async def test_pending_tournament_shows_no_placement_yet(client, db_session):
    player, user = await make_player(db_session, username="history_pending")
    my_automaton_id = str(uuid.uuid4())

    tournament = Tournament(
        type="unranked",
        status="running",
        entrants=[
            _entrant(
                user_id=user.id,
                automaton_id=my_automaton_id,
                automaton_name="Bot",
                username=user.username,
            ),
        ],
        result=None,
    )
    db_session.add(tournament)
    await db_session.flush()
    await db_session.commit()

    resp = await player.get("/me/tournaments")
    row = resp.json()[0]
    assert row["placement"] is None
    assert row["voided"] is False
    assert row["status"] == "running"


async def test_only_returns_tournaments_the_caller_participated_in(client, db_session):
    player, _user = await make_player(db_session, username="history_unrelated")
    other_id = str(uuid.uuid4())

    tournament = Tournament(
        type="unranked",
        status="completed",
        entrants=[
            _entrant(
                user_id=other_id,
                automaton_id="opp-only",
                automaton_name="NotMine",
                username="someone_else",
            ),
        ],
        result={"standings": [], "faulted": []},
    )
    db_session.add(tournament)
    await db_session.flush()
    await db_session.commit()

    resp = await player.get("/me/tournaments")
    assert resp.json() == []


async def test_unauthenticated_request_returns_401(client):
    resp = await client.get("/me/tournaments")
    assert resp.status_code == 401
