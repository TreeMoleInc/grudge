"""worker.process_job against a real fixture Tournament/Job, using
grudge_engine's reference bots via DevSandboxBackend - proves the real engine
call (grudge_engine.tournament_runner.run_tournament) plus DB persistence.
Not the real polling loop (run_worker_loop) - process_job is exposed as a
standalone function specifically so it's testable this way (see its
docstring). Progress-relay HTTP calls (services/progress_relay.py) fail fast
with a connection error since no server is listening on internal_base_url
during tests, which progress_relay already treats as non-fatal (logged, not
raised) - no mocking needed for that part.

Entrants are backed by real User/Automaton/AutomatonVersion rows (not the
human-readable-but-fake ids ("allc"/"alld"/"broken") this file used before
Phase 6) - tournament_entries/matches now have real FK columns
(SET NULL on delete, but still enforced-at-insert for a non-NULL value), so a
non-UUID/nonexistent-user fixture would raise at insert time. This is a
deliberate fixture fix, not a defensive guard added to production code - see
services/match_history.py, which stays fail-loud on genuinely bad data.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from grudge_backend.models.automaton import Automaton, AutomatonVersion
from grudge_backend.models.job import Job
from grudge_backend.models.tournament import Match, Tournament, TournamentEntry
from grudge_backend.models.user import User
from grudge_backend.services.jobs import claim_next_job
from grudge_backend.worker import process_job

pytestmark = pytest.mark.integration

_ALWAYS_COOPERATE = "def decide(history):\n    return COOPERATE\n"
_ALWAYS_DEFECT = "def decide(history):\n    return DEFECT\n"
_BROKEN = "def decide(history):\n    raise ValueError('boom')\n"


async def _entrant(db_session, *, name: str, code: str, rating: int = 1000) -> dict:
    """Creates real User/Automaton/AutomatonVersion rows and returns the same
    dict shape services/tournaments.py:create_tournament_and_enqueue builds -
    `name` is just this fixture's own readable label (becomes Automaton.name),
    the actual `automaton_id` in the returned dict is that row's real UUID.
    """
    user = User(username=f"worker_test_{name}_{uuid.uuid4().hex[:8]}", rating=rating)
    db_session.add(user)
    await db_session.flush()

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
        "rating_snapshot": rating,
        "automaton_name": name,
        "owner_username": user.username,
        "automaton_version_name": "v1",
    }


async def _make_tournament_and_job(
    db_session, *, entrants: list[dict], seed: int | None = 1, tournament_type: str = "unranked"
) -> Tournament:
    tournament = Tournament(type=tournament_type, status="pending", entrants=entrants, seed=seed)
    db_session.add(tournament)
    await db_session.flush()
    db_session.add(
        Job(job_type="tournament", status="queued", payload={"tournament_id": str(tournament.id)})
    )
    await db_session.commit()
    return tournament


async def test_process_job_runs_real_tournament_and_persists_result(
    db_session, worker_session_maker
):
    allc = await _entrant(db_session, name="allc", code=_ALWAYS_COOPERATE)
    alld = await _entrant(db_session, name="alld", code=_ALWAYS_DEFECT)
    tournament = await _make_tournament_and_job(db_session, entrants=[allc, alld])

    claimed = await claim_next_job(db_session)
    assert claimed is not None
    assert claimed.status == "running"

    await process_job(claimed, session_maker=worker_session_maker)

    await db_session.refresh(claimed)
    await db_session.refresh(tournament)

    assert claimed.status == "completed"
    assert tournament.status == "completed"
    assert tournament.result is not None
    assert len(tournament.result["matches"]) == 1  # 2 choose 2
    match = tournament.result["matches"][0]
    assert match["status"] == "completed"
    # AllD exploits AllC's cooperation every round - AllD's score is strictly higher.
    a_is_alld = match["automaton_a_id"] == alld["automaton_id"]
    alld_score = match["score_a"] if a_is_alld else match["score_b"]
    allc_score = match["score_b"] if a_is_alld else match["score_a"]
    assert alld_score > allc_score
    assert len(tournament.result["standings"]) == 2
    assert tournament.result["faulted"] == []

    # Phase 4: round-by-round logs are now persisted (previously stripped) to
    # power the Results page's game-by-game drill-down.
    rounds = match["rounds"]
    assert len(rounds) == match["games_played"]
    assert rounds[0]["round_index"] == 0
    assert {rounds[0]["move_a"], rounds[0]["move_b"]} <= {"COOPERATE", "DEFECT"}
    assert rounds[-1]["round_index"] == match["games_played"] - 1


async def test_process_job_voids_faulted_automaton_but_completes_tournament(
    db_session, worker_session_maker
):
    allc = await _entrant(db_session, name="allc", code=_ALWAYS_COOPERATE)
    broken = await _entrant(db_session, name="broken", code=_BROKEN)
    alld = await _entrant(db_session, name="alld", code=_ALWAYS_DEFECT)
    tournament = await _make_tournament_and_job(db_session, entrants=[allc, broken, alld])
    claimed = await claim_next_job(db_session)

    await process_job(claimed, session_maker=worker_session_maker)

    await db_session.refresh(claimed)
    await db_session.refresh(tournament)

    assert claimed.status == "completed"
    assert tournament.status == "completed"  # the tournament as a whole succeeds
    faulted_ids = {f["automaton_id"] for f in tournament.result["faulted"]}
    assert faulted_ids == {broken["automaton_id"]}
    standing_ids = {s["automaton_id"] for s in tournament.result["standings"]}
    assert standing_ids == {allc["automaton_id"], alld["automaton_id"]}


async def test_process_job_persists_relational_tournament_entries_and_matches(
    db_session, worker_session_maker
):
    allc = await _entrant(db_session, name="allc", code=_ALWAYS_COOPERATE)
    broken = await _entrant(db_session, name="broken", code=_BROKEN)
    alld = await _entrant(db_session, name="alld", code=_ALWAYS_DEFECT)
    tournament = await _make_tournament_and_job(db_session, entrants=[allc, broken, alld])
    claimed = await claim_next_job(db_session)

    await process_job(claimed, session_maker=worker_session_maker)

    entries_result = await db_session.execute(
        select(TournamentEntry).where(TournamentEntry.tournament_id == tournament.id)
    )
    entries = entries_result.scalars().all()
    assert {str(e.automaton_id) for e in entries} == {
        allc["automaton_id"],
        broken["automaton_id"],
        alld["automaton_id"],
    }

    matches_result = await db_session.execute(
        select(Match).where(Match.tournament_id == tournament.id)
    )
    matches = matches_result.scalars().all()
    assert len(matches) == 3  # 3 choose 2
    # The broken automaton's matches are still recorded, as "voided" - a real
    # historical fact, not dropped from the relational layer.
    voided = [m for m in matches if m.status == "voided"]
    assert len(voided) == 2
    assert all(
        isinstance(m.rounds, list) for m in matches
    )  # JSONB round log present on every match


async def test_claim_next_job_only_claims_queued_jobs(db_session):
    allc = await _entrant(db_session, name="allc", code=_ALWAYS_COOPERATE)
    await _make_tournament_and_job(db_session, entrants=[allc])

    first = await claim_next_job(db_session)
    assert first is not None
    assert first.status == "running"

    second = await claim_next_job(db_session)
    assert second is None  # nothing left queued
