"""GET /automata/{id}/stats and GET /automata/{id}/head-to-head/{opponent_id} -
the frontend consumer services/match_history.py's automaton_record and
head_to_head_summary were built for (previously proof-of-capability only, see
CLAUDE.md's Phase 6 TODO note). Matches are produced via the real worker
(test_worker.py's helpers), not hand-inserted, so scores/outcomes come from
the actual engine rather than being asserted into existence.
"""

from __future__ import annotations

import uuid

import pytest

from grudge_backend.models.automaton import Automaton, AutomatonVersion
from grudge_backend.models.user import User
from grudge_backend.services.jobs import claim_next_job
from grudge_backend.worker import process_job
from tests.integration.test_worker import (
    _ALWAYS_COOPERATE,
    _ALWAYS_DEFECT,
    _make_tournament_and_job,
)

pytestmark = pytest.mark.integration


async def _entrant_for_user(db_session, *, user: User, name: str, code: str) -> dict:
    """Same shape as test_worker.py's _entrant, but attaches the automaton to
    an EXISTING user (rather than minting a fresh one) - needed here so the
    stats/head-to-head endpoints' ownership check (current_user.id ==
    Automaton.user_id) can be exercised against a real logged-in test client.
    """
    automaton = Automaton(user_id=user.id, name=name, sort_order=0)
    db_session.add(automaton)
    await db_session.flush()

    version = AutomatonVersion(automaton_id=automaton.id, name="v1", code=code)
    db_session.add(version)
    await db_session.flush()

    automaton.active_version_id = version.id
    await db_session.flush()

    return {
        "user_id": str(user.id),
        "automaton_id": str(automaton.id),
        "automaton_version_id": str(version.id),
        "code_snapshot": code,
        "rating_snapshot": user.rating,
        "automaton_name": name,
        "owner_username": user.username,
        "automaton_version_name": "v1",
    }


async def test_stats_for_automaton_with_no_matches_is_all_zero(auth_client, db_session, user):
    mine = await _entrant_for_user(db_session, user=user, name="mine", code=_ALWAYS_COOPERATE)
    await db_session.commit()

    resp = await auth_client.get(f"/automata/{mine['automaton_id']}/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["matches_played"] == 0
    assert body["wins"] == 0
    assert body["losses"] == 0
    assert body["ties"] == 0
    assert body["voided_matches"] == 0
    assert body["average_points_per_game"] == 0.0


async def test_stats_aggregates_across_matches_against_different_opponents(
    auth_client, db_session, user, worker_session_maker
):
    mine = await _entrant_for_user(db_session, user=user, name="mine", code=_ALWAYS_COOPERATE)
    opponent = await _entrant_for_user(db_session, user=user, name="opponent", code=_ALWAYS_DEFECT)
    friend = await _entrant_for_user(db_session, user=user, name="friend", code=_ALWAYS_COOPERATE)
    await db_session.commit()

    # AllC (mine) loses to AllD (opponent) every round.
    await _make_tournament_and_job(db_session, entrants=[mine, opponent], seed=1)
    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)
    # AllC (mine) ties AllC (friend).
    await _make_tournament_and_job(db_session, entrants=[mine, friend], seed=2)
    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)

    resp = await auth_client.get(f"/automata/{mine['automaton_id']}/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["matches_played"] == 2
    assert body["losses"] == 1
    assert body["ties"] == 1
    assert body["wins"] == 0
    assert body["voided_matches"] == 0
    assert body["average_points_per_game"] > 0


async def test_stats_requires_ownership(auth_client, db_session, other_user):
    theirs = await _entrant_for_user(
        db_session, user=other_user, name="theirs", code=_ALWAYS_COOPERATE
    )
    await db_session.commit()

    resp = await auth_client.get(f"/automata/{theirs['automaton_id']}/stats")
    assert resp.status_code == 404


async def test_stats_for_unknown_automaton_is_404(auth_client):
    resp = await auth_client.get(f"/automata/{uuid.uuid4()}/stats")
    assert resp.status_code == 404


async def test_opponents_lists_each_distinct_opponent_with_a_record(
    auth_client, db_session, user, worker_session_maker
):
    mine = await _entrant_for_user(db_session, user=user, name="mine", code=_ALWAYS_COOPERATE)
    rival = await _entrant_for_user(db_session, user=user, name="rival", code=_ALWAYS_DEFECT)
    friend = await _entrant_for_user(db_session, user=user, name="friend", code=_ALWAYS_COOPERATE)
    await db_session.commit()

    await _make_tournament_and_job(db_session, entrants=[mine, rival], seed=1)
    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)
    await _make_tournament_and_job(db_session, entrants=[mine, friend], seed=2)
    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)

    resp = await auth_client.get(f"/automata/{mine['automaton_id']}/opponents")
    assert resp.status_code == 200
    by_id = {o["opponent_automaton_id"]: o for o in resp.json()}
    assert set(by_id) == {rival["automaton_id"], friend["automaton_id"]}
    assert by_id[rival["automaton_id"]]["losses"] == 1
    assert by_id[friend["automaton_id"]]["ties"] == 1


async def test_opponents_is_empty_for_an_automaton_with_no_matches(auth_client, db_session, user):
    mine = await _entrant_for_user(db_session, user=user, name="mine", code=_ALWAYS_COOPERATE)
    await db_session.commit()

    resp = await auth_client.get(f"/automata/{mine['automaton_id']}/opponents")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_opponents_requires_ownership(auth_client, db_session, other_user):
    theirs = await _entrant_for_user(
        db_session, user=other_user, name="theirs", code=_ALWAYS_COOPERATE
    )
    await db_session.commit()

    resp = await auth_client.get(f"/automata/{theirs['automaton_id']}/opponents")
    assert resp.status_code == 404


async def test_head_to_head_is_scoped_to_the_given_opponent_only(
    auth_client, db_session, user, worker_session_maker
):
    mine = await _entrant_for_user(db_session, user=user, name="mine", code=_ALWAYS_COOPERATE)
    rival = await _entrant_for_user(db_session, user=user, name="rival", code=_ALWAYS_DEFECT)
    bystander = await _entrant_for_user(
        db_session, user=user, name="bystander", code=_ALWAYS_COOPERATE
    )
    await db_session.commit()

    await _make_tournament_and_job(db_session, entrants=[mine, rival], seed=1)
    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)
    # A match against a third automaton must NOT show up in the mine-vs-rival view.
    await _make_tournament_and_job(db_session, entrants=[mine, bystander], seed=2)
    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)

    resp = await auth_client.get(
        f"/automata/{mine['automaton_id']}/head-to-head/{rival['automaton_id']}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["opponent_automaton_id"] == rival["automaton_id"]
    assert body["opponent_name"] == "rival"
    assert len(body["matches"]) == 1
    assert body["losses"] == 1
    assert body["wins"] == 0
    assert body["ties"] == 0


async def test_head_to_head_requires_ownership_of_the_first_automaton(
    auth_client, db_session, user, other_user
):
    theirs = await _entrant_for_user(
        db_session, user=other_user, name="theirs", code=_ALWAYS_COOPERATE
    )
    mine = await _entrant_for_user(db_session, user=user, name="mine", code=_ALWAYS_COOPERATE)
    await db_session.commit()

    resp = await auth_client.get(
        f"/automata/{theirs['automaton_id']}/head-to-head/{mine['automaton_id']}"
    )
    assert resp.status_code == 404


async def test_head_to_head_opponent_need_not_be_owned_by_caller(
    auth_client, db_session, user, other_user, worker_session_maker
):
    mine = await _entrant_for_user(db_session, user=user, name="mine", code=_ALWAYS_COOPERATE)
    theirs = await _entrant_for_user(
        db_session, user=other_user, name="theirs", code=_ALWAYS_DEFECT
    )
    await db_session.commit()

    await _make_tournament_and_job(db_session, entrants=[mine, theirs], seed=1)
    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)

    resp = await auth_client.get(
        f"/automata/{mine['automaton_id']}/head-to-head/{theirs['automaton_id']}"
    )
    assert resp.status_code == 200
    assert resp.json()["opponent_owner_username"] == other_user.username
