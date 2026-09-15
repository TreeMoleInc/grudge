"""Internal-only endpoints the worker/watchdog processes call to relay
realtime events into this web process's in-memory WebSocket connections - see
services/progress_relay.py for the sending side. Never browser-facing;
guarded by a shared-secret header, not user auth (there is no "current user"
for a background process).
"""

from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Header, HTTPException, Request, status

from grudge_backend.config import settings
from grudge_backend.ws import tournament_manager

router = APIRouter(prefix="/internal", tags=["internal"])


def _check_secret(x_internal_secret: str | None) -> None:
    # Constant-time comparison - a plain `!=` leaks how many leading
    # characters matched via response timing, letting a network attacker
    # brute-force internal_shared_secret faster than a blind guess would
    # allow. This endpoint is on the same public port as every browser route
    # (see the module docstring), so that timing channel is reachable.
    if not x_internal_secret or not secrets.compare_digest(
        x_internal_secret, settings.internal_shared_secret
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad internal secret.")


@router.post("/tournaments/{tournament_id}/progress", status_code=204)
async def relay_tournament_progress(
    tournament_id: uuid.UUID,
    request: Request,
    x_internal_secret: str | None = Header(default=None),
) -> None:
    _check_secret(x_internal_secret)
    payload = await request.json()
    target_user_id = payload.get("target_user_id")
    message = {"type": payload["type"], "data": payload["data"]}
    await tournament_manager.broadcast(
        str(tournament_id),
        message,
        target_user_id=uuid.UUID(target_user_id) if target_user_id else None,
    )
