"""GET /tournaments/{id} - specifically the rating_delta field added to each
entrant (Phase 6 follow-up), sourced from rating_history. Real tournament
lifecycle behavior (worker persistence, standings, faulted handling) is
already covered by test_worker.py/test_rating_integration.py - this file is
scoped to what this one endpoint adds on top of the raw JSONB entrants.
"""

from __future__ import annotations

import pytest

from grudge_backend.services.jobs import claim_next_job
from grudge_backend.worker import process_job
from tests.integration.test_worker import (
    _ALWAYS_COOPERATE,
    _ALWAYS_DEFECT,
    _BROKEN,
    _entrant,
    _make_tournament_and_job,
)

pytestmark = pytest.mark.integration


async def test_ranked_tournament_reports_rating_delta_per_entrant(
    auth_client, db_session, worker_session_maker
):
    allc = await _entrant(db_session, name="allc", code=_ALWAYS_COOPERATE)
    alld = await _entrant(db_session, name="alld", code=_ALWAYS_DEFECT)
    tournament = await _make_tournament_and_job(
        db_session, entrants=[allc, alld], seed=1, tournament_type="ranked"
    )
    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)

    resp = await auth_client.get(f"/tournaments/{tournament.id}")
    assert resp.status_code == 200
    entrants_by_automaton = {e["automaton_id"]: e for e in resp.json()["entrants"]}

    # AllD exploits AllC every round - AllD gains rating, AllC loses it.
    assert entrants_by_automaton[alld["automaton_id"]]["rating_delta"] > 0
    assert entrants_by_automaton[allc["automaton_id"]]["rating_delta"] < 0


async def test_unranked_tournament_reports_no_rating_delta(
    auth_client, db_session, worker_session_maker
):
    allc = await _entrant(db_session, name="allc", code=_ALWAYS_COOPERATE)
    alld = await _entrant(db_session, name="alld", code=_ALWAYS_DEFECT)
    tournament = await _make_tournament_and_job(
        db_session, entrants=[allc, alld], seed=1, tournament_type="unranked"
    )
    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)

    resp = await auth_client.get(f"/tournaments/{tournament.id}")
    assert resp.status_code == 200
    assert all(e["rating_delta"] is None for e in resp.json()["entrants"])


async def test_faulted_entrant_reports_no_rating_delta_even_in_a_ranked_tournament(
    auth_client, db_session, worker_session_maker
):
    allc = await _entrant(db_session, name="allc", code=_ALWAYS_COOPERATE)
    broken = await _entrant(db_session, name="broken", code=_BROKEN)
    alld = await _entrant(db_session, name="alld", code=_ALWAYS_DEFECT)
    tournament = await _make_tournament_and_job(
        db_session, entrants=[allc, broken, alld], seed=1, tournament_type="ranked"
    )
    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)

    resp = await auth_client.get(f"/tournaments/{tournament.id}")
    assert resp.status_code == 200
    entrants_by_automaton = {e["automaton_id"]: e for e in resp.json()["entrants"]}
    assert entrants_by_automaton[broken["automaton_id"]]["rating_delta"] is None
    assert entrants_by_automaton[allc["automaton_id"]]["rating_delta"] is not None
    assert entrants_by_automaton[alld["automaton_id"]]["rating_delta"] is not None
