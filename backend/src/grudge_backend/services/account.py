"""Account deletion. Confirmed design (2026-08-30): hard-delete the `users`
row and let the database's own ON DELETE CASCADE network do almost all of the
work - every FK referencing `users.id` in this schema already cascades (auth
identities, sessions, automata/versions/folders, friend graph + visibility
settings, sim room ownership/entries/invites, matchmaking queue entries), so
one DELETE naturally removes the account's email/avatar/provider identities,
logs out every session, deletes their automata, and breaks every friendship -
without needing bespoke cleanup code for each of those.

The one thing that ISN'T a live FK and therefore doesn't cascade: a
tournament's `entrants` JSONB is a frozen, point-in-time snapshot (CLAUDE.md
S2 - "match history must store an immutable code snapshot... not a live
foreign-key reference"), including `owner_username`. Keeping match/tournament
history (an explicit product requirement) while still anonymizing the name
shown in it means rewriting that historical JSONB in place, once, before the
user row goes away - there's no live join to fall back on later.

`tournament_entries` (Phase 6's relational mirror of `entrants`) needs the same
treatment for the same reason, even though its `user_id` column IS a real FK
(SET NULL, not CASCADE - see models/tournament.py) - `owner_username` there is
still a plain snapshot column, not a live join, so it wouldn't update itself
just because `user_id` goes to NULL on delete.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.models.sim_room import SimRoom, SimRoomEntry
from grudge_backend.models.tournament import Tournament, TournamentEntry
from grudge_backend.models.user import User
from grudge_backend.models.waiting_room import MatchmakingQueueEntry

# Mirrors the three "currently active" states services/stats.py sums for the
# home page's in_activity_count, scoped here to one user as a yes/no gate
# instead of a count. Kept as a separate scoped query rather than importing
# and filtering stats.py's aggregate, since the two need different shapes
# (a fast EXISTS-style check here vs. three summed counts there).
_PROCESSING_TOURNAMENT_STATUSES = ("pending", "running")


class AccountCurrentlyActiveError(Exception):
    pass


def _anonymized_label(user_id: uuid.UUID) -> str:
    # A short slice of the user's own id, not a new counter/table - stable
    # and distinguishable across different deleted accounts (CLAUDE.md S2's
    # confirmed design) without needing anywhere new to persist a sequence.
    return f"[user-deleted-{str(user_id)[:8]}]"


async def _is_currently_active(db: AsyncSession, *, user_id: uuid.UUID) -> bool:
    waiting = await db.execute(
        select(func.count())
        .select_from(MatchmakingQueueEntry)
        .where(MatchmakingQueueEntry.user_id == user_id, MatchmakingQueueEntry.status == "waiting")
    )
    if waiting.scalar_one() > 0:
        return True

    in_open_room = await db.execute(
        select(func.count())
        .select_from(SimRoomEntry)
        .join(SimRoom, SimRoom.id == SimRoomEntry.sim_room_id)
        .where(SimRoomEntry.user_id == user_id, SimRoom.status == "open")
    )
    if in_open_room.scalar_one() > 0:
        return True

    # A user can own an open room without having entered an automaton into it
    # themselves (create_room doesn't auto-add an entry for the owner) - the
    # check above alone misses that case. Without this, deleting such an
    # account CASCADEs SimRoom.owner_user_id -> ON DELETE, which in turn
    # CASCADEs every other entrant's SimRoomEntry away with them, silently
    # destroying OTHER players' room state instead of going through
    # sim_rooms.leave_room's confirmed ownership-transfer-to-earliest-entrant
    # rule (CLAUDE.md S2).
    owns_open_room = await db.execute(
        select(func.count())
        .select_from(SimRoom)
        .where(SimRoom.owner_user_id == user_id, SimRoom.status == "open")
    )
    if owns_open_room.scalar_one() > 0:
        return True

    in_processing_tournament = await db.execute(
        select(Tournament.id)
        .where(
            Tournament.status.in_(_PROCESSING_TOURNAMENT_STATUSES),
            Tournament.entrants.contains([{"user_id": str(user_id)}]),
        )
        .limit(1)
    )
    return in_processing_tournament.scalar_one_or_none() is not None


async def _anonymize_tournament_history(db: AsyncSession, *, user_id: uuid.UUID) -> None:
    label = _anonymized_label(user_id)
    result = await db.execute(
        select(Tournament).where(Tournament.entrants.contains([{"user_id": str(user_id)}]))
    )
    for tournament in result.scalars().all():
        # Full reassignment, not an in-place list/dict mutation - SQLAlchemy
        # only detects a JSONB column as changed on attribute set, not on
        # mutating the Python object it already holds.
        tournament.entrants = [
            {**entrant, "owner_username": label}
            if entrant.get("user_id") == str(user_id)
            else entrant
            for entrant in tournament.entrants
        ]

    await db.execute(
        update(TournamentEntry)
        .where(TournamentEntry.user_id == user_id)
        .values(owner_username=label)
    )


async def delete_account(db: AsyncSession, *, user: User) -> None:
    if await _is_currently_active(db, user_id=user.id):
        raise AccountCurrentlyActiveError(
            "Can't delete your account while you're in an active queue, room, or tournament. "
            "Leave first, then try again."
        )

    await _anonymize_tournament_history(db, user_id=user.id)
    await db.delete(user)
    await db.flush()
