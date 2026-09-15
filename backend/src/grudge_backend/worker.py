"""Background worker: claims queued tournament jobs and runs them for real via
grudge_engine.tournament_runner.run_tournament(...). Run as its own process:
`python -m grudge_backend.worker`. Per CLAUDE.md S3, this should run under a
supervisor with auto-restart (systemd Restart=always) in production - the
watchdog (watchdog.py) is what catches the specific job orphaned by a crash,
not this process catching its own death.

Sandbox backend note: which grudge_engine backend actually runs automaton
code is controlled by `settings.sandbox_backend` ("dev" or "nsjail" - see
config.py) via `sandbox.build_sandbox_backend()` (shared with the web
process's pre-flight check, services/preflight.py - see sandbox.py's own
docstring for the full swap-to-nsjail-in-production note).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime

from grudge_engine.automaton import Automaton
from grudge_engine.results import MatchResult, TournamentResult
from grudge_engine.tournament_runner import run_tournament
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.db import async_session_maker
from grudge_backend.models.job import Job
from grudge_backend.models.tournament import Tournament
from grudge_backend.sandbox import build_sandbox_backend
from grudge_backend.services.jobs import HEARTBEAT_INTERVAL_SECONDS, claim_next_job, tick_heartbeat
from grudge_backend.services.match_history import record_tournament_result
from grudge_backend.services.notifications import create_flagged_notifications
from grudge_backend.services.progress_relay import (
    notify_automaton_flagged,
    notify_tournament_completed,
    notify_tournament_error,
    notify_tournament_progress,
)
from grudge_backend.services.rating import apply_rating_update

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1.0


def _match_to_dict(m: MatchResult) -> dict:
    # Full round-by-round move/point logs ARE persisted (Phase 4 decision - see
    # TODO.md) to power the Results page's game-by-game drill-down. Player debug
    # output (print() logs) is still NOT persisted - no retention policy exists
    # for that yet and it isn't needed for the round log itself.
    return {
        "automaton_a_id": m.automaton_a_id,
        "automaton_b_id": m.automaton_b_id,
        "games_played": m.games_played,
        "score_a": m.score_a,
        "score_b": m.score_b,
        "status": m.status,
        "voided_side": m.voided_side,
        "void_reason": m.void_reason,
        "rounds": [
            {
                "round_index": r.round_index,
                "move_a": r.move_a,
                "move_b": r.move_b,
                "points_a": r.points_a,
                "points_b": r.points_b,
            }
            for r in m.rounds
        ],
    }


def result_to_dict(result: TournamentResult) -> dict:
    return {
        "automaton_ids": list(result.automaton_ids),
        "matches": [_match_to_dict(m) for m in result.matches],
        "standings": [
            {
                "automaton_id": s.automaton_id,
                "total_points": s.total_points,
                "total_games": s.total_games,
                "points_per_game": s.points_per_game,
            }
            for s in result.standings
        ],
        "faulted": [
            {
                "automaton_id": f.automaton_id,
                "reason": f.reason,
                "voided_match_ids": [list(pair) for pair in f.voided_match_ids],
            }
            for f in result.faulted
        ],
    }


SessionMaker = Callable[[], AbstractAsyncContextManager[AsyncSession]]


async def _heartbeat_loop(
    job_id: uuid.UUID, stop_event: asyncio.Event, session_maker: SessionMaker
) -> None:
    while not stop_event.is_set():
        async with session_maker() as db:
            await tick_heartbeat(db, job_id=job_id)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=HEARTBEAT_INTERVAL_SECONDS)
        except TimeoutError:
            pass


async def _fail_job_and_tournament(
    job_id: uuid.UUID, tournament_id: uuid.UUID, error: str, session_maker: SessionMaker
) -> None:
    async with session_maker() as db:
        job = await db.get(Job, job_id)
        if job is not None:
            job.status = "failed"
            job.last_error = error
            job.finished_at = datetime.now(UTC)

        tournament = await db.get(Tournament, tournament_id)
        if tournament is not None:
            tournament.status = "failed_voided"
            tournament.error_message = error
        await db.commit()

    await notify_tournament_error(
        tournament_id,
        reason="tournament_error",
        message="Tournament failed and was fully voided - no ratings were affected.",
    )


async def process_job(job: Job, *, session_maker: SessionMaker = async_session_maker) -> None:
    """Exposed as a standalone function (rather than only the private loop
    below) so tests can call it directly against a fixture job, without
    spawning the real polling process. `session_maker` defaults to the real
    app-wide sessionmaker; tests inject one bound to their own
    savepoint-per-test connection (see tests/integration/test_worker.py) so
    this function's several internal `async with session_maker() as db:`
    blocks see the same uncommitted fixture data the test set up.
    """
    tournament_id = uuid.UUID(job.payload["tournament_id"])

    async with session_maker() as db:
        tournament = await db.get(Tournament, tournament_id)
        tournament.status = "running"
        tournament.started_at = datetime.now(UTC)
        entrants = list(tournament.entrants)
        seed = tournament.seed
        await db.commit()

    automata = [Automaton(id=e["automaton_id"], source=e["code_snapshot"] or "") for e in entrants]

    loop = asyncio.get_running_loop()

    def on_match_complete(_match_result: MatchResult, completed: int, total: int) -> None:
        # Called synchronously from run_tournament, which itself runs on a
        # worker thread (see asyncio.to_thread below) - schedule the actual
        # async HTTP push back onto the main event loop rather than blocking
        # the tournament run on it. Must never raise (grudge_engine aborts the
        # tournament if this callback raises) - failures are logged only.
        async def _push() -> None:
            try:
                await notify_tournament_progress(tournament_id, completed=completed, total=total)
            except Exception:
                logger.exception("progress push failed for tournament %s", tournament_id)

        asyncio.run_coroutine_threadsafe(_push(), loop)

    stop_heartbeat = asyncio.Event()
    heartbeat_task = asyncio.create_task(_heartbeat_loop(job.id, stop_heartbeat, session_maker))

    try:
        result = await asyncio.to_thread(
            run_tournament,
            automata,
            build_sandbox_backend(),
            seed=seed,
            on_match_complete=on_match_complete,
        )
    except Exception as exc:  # noqa: BLE001 - genuinely any failure here (sandbox
        # crash, engine bug) must fail-safe into "void the tournament, alert
        # the owner", not propagate and strand the job silently.
        stop_heartbeat.set()
        await heartbeat_task
        await _fail_job_and_tournament(job.id, tournament_id, str(exc), session_maker)
        return

    stop_heartbeat.set()
    await heartbeat_task

    async with session_maker() as db:
        job_row = await db.get(Job, job.id)
        job_row.status = "completed"
        job_row.finished_at = datetime.now(UTC)

        tournament = await db.get(Tournament, tournament_id)
        tournament.status = "completed"
        tournament.completed_at = datetime.now(UTC)
        tournament.result = result_to_dict(result)

        # Phase 6: all three share this same completion transaction - atomic
        # with the tournament row's own completion, no new transaction
        # boundaries introduced.
        await record_tournament_result(db, tournament=tournament, result=result, entrants=entrants)
        if tournament.type == "ranked":
            await apply_rating_update(db, tournament=tournament, result=result, entrants=entrants)
        await create_flagged_notifications(
            db, tournament=tournament, result=result, entrants=entrants
        )

        await db.commit()

    await notify_tournament_completed(tournament_id, redirect_url=f"/results/{tournament_id}")

    for faulted in result.faulted:
        owner_user_id = next(
            (e["user_id"] for e in entrants if e["automaton_id"] == faulted.automaton_id), None
        )
        if owner_user_id is not None:
            await notify_automaton_flagged(
                tournament_id,
                target_user_id=owner_user_id,
                automaton_id=faulted.automaton_id,
                reason=faulted.reason,
            )


async def run_worker_loop() -> (
    None
):  # pragma: no cover - exercised via process_job directly in tests
    logger.info("worker started, polling every %.1fs", POLL_INTERVAL_SECONDS)
    while True:
        async with async_session_maker() as db:
            job = await claim_next_job(db)
        if job is None:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            continue
        try:
            await process_job(job)
        except Exception:
            logger.exception("unhandled error processing job %s", job.id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker_loop())
