"""Job-queue primitives: atomic claim (worker) and stale-heartbeat sweep
(watchdog). Both use plain Postgres SQL (SELECT ... FOR UPDATE SKIP LOCKED,
and a single atomic UPDATE ... WHERE ... RETURNING) - no new infrastructure,
per CLAUDE.md's explicit "avoid adding Redis until actual concurrent volume
needs it" framing. Each function owns its own transaction (commits directly)
since these are called as standalone operations by the worker/watchdog loops,
not nested inside a larger request-scoped transaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.models.job import Job

HEARTBEAT_INTERVAL_SECONDS = 5
# 6x the heartbeat interval - generous enough to absorb scheduling jitter
# without false-triggering (CLAUDE.md S3).
STALE_HEARTBEAT_SECONDS = 30


async def claim_next_job(db: AsyncSession) -> Job | None:
    result = await db.execute(
        text(
            """
            UPDATE jobs SET status = 'running', started_at = now(), heartbeat_at = now()
            WHERE id = (
                SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at
                FOR UPDATE SKIP LOCKED LIMIT 1
            )
            RETURNING id
            """
        )
    )
    row = result.first()
    await db.commit()
    if row is None:
        return None
    return await db.get(Job, row[0])


async def tick_heartbeat(db: AsyncSession, *, job_id: uuid.UUID) -> None:
    job = await db.get(Job, job_id)
    if job is not None:
        job.heartbeat_at = datetime.now(UTC)
        await db.commit()


async def sweep_stale_jobs(db: AsyncSession, *, now: datetime | None = None) -> list[uuid.UUID]:
    """Atomically fails any 'running' job whose heartbeat has gone stale -
    covers both a single hung job and the whole worker process dying, without
    needing to distinguish which (CLAUDE.md S3). Returns the ids of jobs that
    were just flipped, so the caller can act on their tournaments.
    """
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(seconds=STALE_HEARTBEAT_SECONDS)
    result = await db.execute(
        text(
            """
            UPDATE jobs SET status = 'failed', last_error = 'stale heartbeat', finished_at = now()
            WHERE status = 'running' AND heartbeat_at < :cutoff
            RETURNING id
            """
        ),
        {"cutoff": cutoff},
    )
    ids = [row[0] for row in result.fetchall()]
    await db.commit()
    return ids
