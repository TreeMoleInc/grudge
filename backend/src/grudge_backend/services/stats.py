"""Home-page "live activity" numbers - a public (unauthenticated), deliberately
approximate view of how many people are around right now. Not a realtime/WS
feed (see TODO.md's now-resolved online-counter design note): `online_count`
is derived from `sessions.last_seen_at`, which `auth/session.py` bumps on
every authenticated request (throttled to once per ~30s per session) - so
"online" really means "made a request recently enough to still be here",
not "has a live socket open". Good enough for a rough headline number without
adding a new app-wide presence channel.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.models.session import Session as SessionModel
from grudge_backend.models.sim_room import SimRoom, SimRoomEntry
from grudge_backend.models.tournament import Tournament
from grudge_backend.models.waiting_room import MatchmakingQueueEntry

# How recently a session must have been active to count as "online". Wider
# than the ~30s last_seen_at update throttle so someone browsing (not just
# polling) doesn't flicker in and out between requests.
ONLINE_WINDOW_SECONDS = 120

# A player can only ever be in one of these three states at a time (a
# matchmaking entry flips from "waiting" to "matched" the instant a
# tournament starts; a sim room entry's room flips out of "open" the same
# way), so these are plain counts summed together, not a distinct-across-
# tables query.
_PROCESSING_TOURNAMENT_STATUSES = ("pending", "running")


@dataclass(frozen=True)
class LiveStats:
    online_count: int
    in_activity_count: int


async def get_live_stats(db: AsyncSession, *, now: datetime | None = None) -> LiveStats:
    now = now or datetime.now(UTC)
    online_since = now - timedelta(seconds=ONLINE_WINDOW_SECONDS)

    online_result = await db.execute(
        select(func.count(func.distinct(SessionModel.user_id))).where(
            SessionModel.expires_at > now, SessionModel.last_seen_at >= online_since
        )
    )
    online_count = online_result.scalar_one()

    waiting_result = await db.execute(
        select(func.count()).where(MatchmakingQueueEntry.status == "waiting")
    )
    waiting_count = waiting_result.scalar_one()

    in_room_result = await db.execute(
        select(func.count())
        .select_from(SimRoomEntry)
        .join(SimRoom, SimRoom.id == SimRoomEntry.sim_room_id)
        .where(SimRoom.status == "open")
    )
    in_room_count = in_room_result.scalar_one()

    processing_result = await db.execute(
        select(Tournament.entrants).where(Tournament.status.in_(_PROCESSING_TOURNAMENT_STATUSES))
    )
    processing_count = sum(len(entrants) for entrants in processing_result.scalars().all())

    return LiveStats(
        online_count=online_count,
        in_activity_count=waiting_count + in_room_count + processing_count,
    )
