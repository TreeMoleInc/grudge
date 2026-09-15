"""Client-side helpers the worker/watchdog (separate OS processes from the web
process, per CLAUDE.md S3's explicit systemd/"separate independent watchdog"
framing) use to push realtime updates into the web process - see
routers/internal.py for the receiving side. An internal HTTP callback rather
than Postgres LISTEN/NOTIFY: simpler and more testable, consistent with this
project's low-moving-parts philosophy (documented judgment call, see TODO.md).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from grudge_backend.config import settings

logger = logging.getLogger(__name__)


async def _post_internal(path: str, payload: dict[str, Any]) -> None:
    url = f"{settings.internal_base_url}{path}"
    headers = {"X-Internal-Secret": settings.internal_shared_secret}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
    except httpx.HTTPError:
        # A failed relay must never abort the tournament run/watchdog sweep
        # that triggered it - it only means a live viewer misses one update.
        logger.exception("internal progress relay failed: POST %s", path)


async def notify_tournament_progress(
    tournament_id: uuid.UUID, *, completed: int, total: int
) -> None:
    pct = round(100 * completed / total, 1) if total else 0.0
    await _post_internal(
        f"/internal/tournaments/{tournament_id}/progress",
        {
            "type": "progress",
            "data": {"completed_matches": completed, "total_matches": total, "pct": pct},
        },
    )


async def notify_tournament_completed(tournament_id: uuid.UUID, *, redirect_url: str) -> None:
    await _post_internal(
        f"/internal/tournaments/{tournament_id}/progress",
        {"type": "completed", "data": {"redirect_url": redirect_url}},
    )


async def notify_tournament_error(tournament_id: uuid.UUID, *, reason: str, message: str) -> None:
    await _post_internal(
        f"/internal/tournaments/{tournament_id}/progress",
        {"type": "error", "data": {"reason": reason, "message": message}},
    )


async def notify_automaton_flagged(
    tournament_id: uuid.UUID, *, target_user_id: str, automaton_id: str, reason: str
) -> None:
    """Pushed on the same tournament channel as the rest of the progress
    events, but the web process only forwards it to `target_user_id`'s
    connection (see routers/internal.py) - the "flagged privately to its
    owner" mechanism, live-connection-only for Phase 3 (CLAUDE.md S2's fuller
    "flagged privately... not shown in normal match history" is a durable,
    offline-capable notification concept deferred to Phase 6 - see TODO.md).
    """
    await _post_internal(
        f"/internal/tournaments/{tournament_id}/progress",
        {
            "type": "automaton_flagged",
            "target_user_id": target_user_id,
            "data": {"automaton_id": automaton_id, "reason": reason},
        },
    )
