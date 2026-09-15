"""Independent watchdog process: scans for 'running' jobs whose heartbeat has
gone stale and fails them (and their tournaments), fully voided - covers both
a single hung job and the whole worker process dying, without needing to
distinguish which (CLAUDE.md S3: "not the worker itself - it can't detect its
own death"). Also runs the matchmaking heartbeat-eviction and starvation-
backstop sweeps, and an expired-session cleanup sweep (same 15-30s cadence, so
they share this process rather than needing a fourth/fifth one). Run as
`python -m grudge_backend.watchdog`.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

import httpx

from grudge_backend.auth.session import sweep_expired_sessions
from grudge_backend.config import settings
from grudge_backend.db import async_session_maker
from grudge_backend.models.job import Job
from grudge_backend.models.tournament import Tournament
from grudge_backend.services import matchmaking
from grudge_backend.services.jobs import sweep_stale_jobs
from grudge_backend.services.progress_relay import notify_tournament_error
from grudge_backend.worker import SessionMaker
from grudge_backend.ws import matchmaking_manager

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 20  # within CLAUDE.md's specified 15-30s cadence


async def _alert_discord(message: str) -> None:
    if not settings.discord_webhook_url:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(settings.discord_webhook_url, json={"content": message})
            resp.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Discord webhook alert failed")


async def handle_stale_jobs(*, session_maker: SessionMaker = async_session_maker) -> None:
    async with session_maker() as db:
        stale_job_ids = await sweep_stale_jobs(db)

    for job_id in stale_job_ids:
        async with session_maker() as db:
            job = await db.get(Job, job_id)
            tournament_id = uuid.UUID(job.payload["tournament_id"])
            tournament = await db.get(Tournament, tournament_id)
            if tournament is not None:
                tournament.status = "failed_voided"
                tournament.error_message = "stale heartbeat - infrastructure fault"
            await db.commit()

        await notify_tournament_error(
            tournament_id,
            reason="stale_heartbeat",
            message="Tournament failed and was fully voided - no ratings were affected.",
        )
        await _alert_discord(
            f":warning: Tournament `{tournament_id}` failed - stale worker heartbeat."
        )


async def handle_matchmaking_sweeps(*, session_maker: SessionMaker = async_session_maker) -> None:
    now = datetime.now(UTC)

    async with session_maker() as db:
        affected_rooms = await matchmaking.sweep_stale_entries(db, now=now)
        await db.commit()
    for room_id in affected_rooms:
        await matchmaking_manager.broadcast(
            str(room_id), {"type": "count_update", "data": {"room_id": str(room_id)}}
        )

    async with session_maker() as db:
        started = await matchmaking.sweep_ranked_starvation(db, now=now)
        await db.commit()
    for tournament, room_id in started:
        await matchmaking_manager.broadcast(
            str(room_id), {"type": "matched", "data": {"tournament_id": str(tournament.id)}}
        )


async def handle_expired_sessions(*, session_maker: SessionMaker = async_session_maker) -> int:
    async with session_maker() as db:
        deleted = await sweep_expired_sessions(db)
        await db.commit()
    if deleted:
        logger.info("swept %d expired session(s)", deleted)
    return deleted


async def run_watchdog_loop() -> (
    None
):  # pragma: no cover - exercised via the handlers directly in tests
    logger.info("watchdog started, sweeping every %ds", SWEEP_INTERVAL_SECONDS)
    while True:
        try:
            await handle_stale_jobs()
            await handle_matchmaking_sweeps()
            await handle_expired_sessions()
        except Exception:
            logger.exception("unhandled error in watchdog sweep")
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_watchdog_loop())
