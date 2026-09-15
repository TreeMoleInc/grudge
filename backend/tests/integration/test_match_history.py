"""services/match_history.py's head_to_head_matches - the proof-of-capability
query the relational tournament_entries/matches tables exist for. Uses the
worker's real process_job to populate real data rather than hand-inserting
Match rows, so this also doubles as another end-to-end check of the Phase 6
worker wiring.
"""

from __future__ import annotations

import uuid

import pytest

from grudge_backend.services.jobs import claim_next_job
from grudge_backend.services.match_history import head_to_head_matches
from grudge_backend.worker import process_job
from tests.integration.test_worker import (
    _ALWAYS_COOPERATE,
    _ALWAYS_DEFECT,
    _entrant,
    _make_tournament_and_job,
)

pytestmark = pytest.mark.integration


async def test_head_to_head_finds_matches_regardless_of_side_ordering(
    db_session, worker_session_maker
):
    allc = await _entrant(db_session, name="allc", code=_ALWAYS_COOPERATE)
    alld = await _entrant(db_session, name="alld", code=_ALWAYS_DEFECT)

    await _make_tournament_and_job(db_session, entrants=[allc, alld], seed=1)
    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)

    matches = await head_to_head_matches(
        db_session,
        automaton_a_id=uuid.UUID(allc["automaton_id"]),
        automaton_b_id=uuid.UUID(alld["automaton_id"]),
    )
    assert len(matches) == 1

    # Same pair, arguments swapped - must find the same match.
    matches_swapped = await head_to_head_matches(
        db_session,
        automaton_a_id=uuid.UUID(alld["automaton_id"]),
        automaton_b_id=uuid.UUID(allc["automaton_id"]),
    )
    assert len(matches_swapped) == 1
    assert matches[0].id == matches_swapped[0].id


async def test_head_to_head_spans_multiple_tournaments(db_session, worker_session_maker):
    allc = await _entrant(db_session, name="allc", code=_ALWAYS_COOPERATE)
    alld = await _entrant(db_session, name="alld", code=_ALWAYS_DEFECT)

    await _make_tournament_and_job(db_session, entrants=[allc, alld], seed=1)
    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)

    # Same two automata, a second separate tournament.
    await _make_tournament_and_job(db_session, entrants=[allc, alld], seed=2)
    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)

    matches = await head_to_head_matches(
        db_session,
        automaton_a_id=uuid.UUID(allc["automaton_id"]),
        automaton_b_id=uuid.UUID(alld["automaton_id"]),
    )
    assert len(matches) == 2
    assert matches[0].created_at <= matches[1].created_at  # oldest first


async def test_head_to_head_excludes_unrelated_matches(db_session, worker_session_maker):
    allc = await _entrant(db_session, name="allc", code=_ALWAYS_COOPERATE)
    alld = await _entrant(db_session, name="alld", code=_ALWAYS_DEFECT)
    other = await _entrant(db_session, name="other", code=_ALWAYS_COOPERATE)

    await _make_tournament_and_job(db_session, entrants=[allc, alld, other], seed=1)
    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)

    matches = await head_to_head_matches(
        db_session,
        automaton_a_id=uuid.UUID(allc["automaton_id"]),
        automaton_b_id=uuid.UUID(other["automaton_id"]),
    )
    assert len(matches) == 1
    ids = {matches[0].automaton_a_id, matches[0].automaton_b_id}
    assert ids == {uuid.UUID(allc["automaton_id"]), uuid.UUID(other["automaton_id"])}
