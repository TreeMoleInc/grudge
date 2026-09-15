"""End-to-end Elo rating updates via the real worker (services/rating.py's
apply_rating_update, wired into worker.py's completion transaction). The pure
math itself is covered by tests/unit/test_rating.py - this file proves the
DB wiring: only ranked tournaments touch rating, faulted automata are fully
excluded, and rating_history rows land correctly.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from grudge_backend.models.rating import RatingHistory
from grudge_backend.models.user import User
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


async def test_ranked_tournament_updates_ratings_and_writes_history(
    db_session, worker_session_maker
):
    allc = await _entrant(db_session, name="allc", code=_ALWAYS_COOPERATE, rating=1000)
    alld = await _entrant(db_session, name="alld", code=_ALWAYS_DEFECT, rating=1000)
    tournament = await _make_tournament_and_job(
        db_session, entrants=[allc, alld], seed=1, tournament_type="ranked"
    )

    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)

    allc_user = await db_session.get(User, uuid.UUID(allc["user_id"]))
    alld_user = await db_session.get(User, uuid.UUID(alld["user_id"]))
    await db_session.refresh(allc_user)
    await db_session.refresh(alld_user)

    assert allc_user.ranked_tournaments_played == 1
    assert alld_user.ranked_tournaments_played == 1
    # AllD exploits AllC every round - AllD should gain rating, AllC should lose it.
    assert alld_user.rating > 1000
    assert allc_user.rating < 1000

    history_result = await db_session.execute(
        select(RatingHistory).where(RatingHistory.tournament_id == tournament.id)
    )
    history_rows = history_result.scalars().all()
    assert len(history_rows) == 2
    assert {h.user_id for h in history_rows} == {allc_user.id, alld_user.id}
    for row in history_rows:
        assert row.rating_before == 1000
        assert row.ranked_tournaments_played_before == 0


async def test_unranked_tournament_never_touches_rating(db_session, worker_session_maker):
    allc = await _entrant(db_session, name="allc", code=_ALWAYS_COOPERATE, rating=1000)
    alld = await _entrant(db_session, name="alld", code=_ALWAYS_DEFECT, rating=1000)
    tournament = await _make_tournament_and_job(
        db_session, entrants=[allc, alld], seed=1, tournament_type="unranked"
    )

    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)

    allc_user = await db_session.get(User, uuid.UUID(allc["user_id"]))
    await db_session.refresh(allc_user)
    assert allc_user.rating == 1000
    assert allc_user.ranked_tournaments_played == 0

    # Scoped to this test's own tournament, not the whole table - other tests
    # share this session and may have their own rating_history rows.
    history_result = await db_session.execute(
        select(RatingHistory).where(RatingHistory.tournament_id == tournament.id)
    )
    assert history_result.scalars().all() == []


async def test_sim_tournament_never_touches_rating(db_session, worker_session_maker):
    allc = await _entrant(db_session, name="allc", code=_ALWAYS_COOPERATE, rating=1000)
    alld = await _entrant(db_session, name="alld", code=_ALWAYS_DEFECT, rating=1000)
    await _make_tournament_and_job(db_session, entrants=[allc, alld], seed=1, tournament_type="sim")

    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)

    allc_user = await db_session.get(User, uuid.UUID(allc["user_id"]))
    await db_session.refresh(allc_user)
    assert allc_user.rating == 1000


async def test_faulted_automatons_owner_is_fully_excluded(db_session, worker_session_maker):
    allc = await _entrant(db_session, name="allc", code=_ALWAYS_COOPERATE, rating=1000)
    broken = await _entrant(db_session, name="broken", code=_BROKEN, rating=1000)
    alld = await _entrant(db_session, name="alld", code=_ALWAYS_DEFECT, rating=1000)
    tournament = await _make_tournament_and_job(
        db_session, entrants=[allc, broken, alld], seed=1, tournament_type="ranked"
    )

    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)

    broken_user = await db_session.get(User, uuid.UUID(broken["user_id"]))
    await db_session.refresh(broken_user)
    # The faulted automaton's owner never entered the rating pool at all -
    # no rating change, no ranked_tournaments_played increment either.
    assert broken_user.rating == 1000
    assert broken_user.ranked_tournaments_played == 0

    history_result = await db_session.execute(
        select(RatingHistory).where(RatingHistory.tournament_id == tournament.id)
    )
    history_rows = history_result.scalars().all()
    assert broken_user.id not in {h.user_id for h in history_rows}
    assert len(history_rows) == 2  # allc + alld only


async def test_fewer_than_two_survivors_skips_rating_but_still_increments_counter(
    db_session, worker_session_maker
):
    # Two of three fault, leaving one survivor - E_i's n*(n-1) divisor is
    # undefined for n=1, so the rating change is skipped entirely, but the
    # survivor still "played" the tournament per CLAUDE.md's counter-increments
    # assumption.
    allc = await _entrant(db_session, name="allc", code=_ALWAYS_COOPERATE, rating=1000)
    broken_a = await _entrant(db_session, name="broken_a", code=_BROKEN, rating=1000)
    broken_b = await _entrant(db_session, name="broken_b", code=_BROKEN, rating=1000)
    tournament = await _make_tournament_and_job(
        db_session, entrants=[allc, broken_a, broken_b], seed=1, tournament_type="ranked"
    )

    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)

    allc_user = await db_session.get(User, uuid.UUID(allc["user_id"]))
    await db_session.refresh(allc_user)
    assert allc_user.rating == 1000  # skipped - no comparison possible
    assert allc_user.ranked_tournaments_played == 1  # still increments

    history_result = await db_session.execute(
        select(RatingHistory).where(RatingHistory.tournament_id == tournament.id)
    )
    assert history_result.scalars().all() == []
