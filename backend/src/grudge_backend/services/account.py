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
from dataclasses import dataclass

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


@dataclass
class ActiveSimRoom:
    room: SimRoom
    is_owner: bool
    entry_id: uuid.UUID | None  # this user's own entry in the room, if any


@dataclass
class ActiveState:
    queue_entry: MatchmakingQueueEntry | None
    sim_rooms: list[ActiveSimRoom]
    tournament_ids: list[uuid.UUID]

    def is_empty(self) -> bool:
        return self.queue_entry is None and not self.sim_rooms and not self.tournament_ids


async def get_active_state(db: AsyncSession, *, user_id: uuid.UUID) -> ActiveState:
    """The same three conditions `_is_currently_active` checks, but returning
    the real rows instead of a yes/no - powers a self-service "what's
    blocking my account deletion" panel (Settings page). Added 2026-09-xx
    after a real support case: a sim room's id lives only in the frontend's
    own React state, never persisted anywhere - a room orphaned by a dropped
    connection or a hard-closed tab (the owner never got to click "Leave
    room") was previously undiscoverable and unleaveable without a direct
    database query, even though `sim_rooms.leave_room` already handles
    exactly this cleanup correctly once a client actually calls it.

    Deliberately reuses the *same* queries `_is_currently_active` runs
    (rather than a cheaper/different shape) so this can never disagree with
    what actually blocks deletion - a player who clears everything this
    returns is guaranteed `delete_account` will then succeed.
    """
    queue_result = await db.execute(
        select(MatchmakingQueueEntry).where(
            MatchmakingQueueEntry.user_id == user_id, MatchmakingQueueEntry.status == "waiting"
        )
    )
    queue_entry = queue_result.scalar_one_or_none()

    owned_result = await db.execute(
        select(SimRoom).where(SimRoom.owner_user_id == user_id, SimRoom.status == "open")
    )
    owned_rooms = {room.id: room for room in owned_result.scalars().all()}

    entry_result = await db.execute(
        select(SimRoom, SimRoomEntry)
        .join(SimRoomEntry, SimRoomEntry.sim_room_id == SimRoom.id)
        .where(SimRoomEntry.user_id == user_id, SimRoom.status == "open")
    )
    # (room, entry) tuples, not just the entry - SimRoomEntry has no `sim_room`
    # relationship declared (models/sim_room.py), so the room object has to
    # come from this query's own join, not looked up off the entry afterward.
    entries_by_room_id = {room.id: (room, entry) for room, entry in entry_result.all()}

    # A union of the two SimRoom sets above, deduplicated by room id - an
    # owner who's also entered their own automaton would otherwise show up
    # as two separate rows for the same room.
    rooms: list[ActiveSimRoom] = []
    for room_id in owned_rooms.keys() | entries_by_room_id.keys():
        owned_room = owned_rooms.get(room_id)
        entry_pair = entries_by_room_id.get(room_id)
        # room_id is drawn from the union of both dicts' keys, so at least
        # one of owned_room/entry_pair is always present here.
        room = owned_room if owned_room is not None else entry_pair[0]
        rooms.append(
            ActiveSimRoom(
                room=room,
                is_owner=owned_room is not None,
                entry_id=entry_pair[1].id if entry_pair is not None else None,
            )
        )

    tournaments_result = await db.execute(
        select(Tournament.id).where(
            Tournament.status.in_(_PROCESSING_TOURNAMENT_STATUSES),
            Tournament.entrants.contains([{"user_id": str(user_id)}]),
        )
    )
    tournament_ids = [row[0] for row in tournaments_result.all()]

    return ActiveState(queue_entry=queue_entry, sim_rooms=rooms, tournament_ids=tournament_ids)


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
