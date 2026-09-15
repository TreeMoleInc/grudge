"""Sim room invite/join system (CLAUDE.md S3: "code/invite join system, owner,
current entry list"). No exact-8 requirement and no waiting room - whatever's
in the entry list when "start" is clicked is the field size.
"""

from __future__ import annotations

import secrets
import string
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.models.sim_room import SimRoom, SimRoomEntry, SimRoomInvite
from grudge_backend.models.tournament import Tournament
from grudge_backend.services.friends import NotFriendsError, are_friends
from grudge_backend.services.tournaments import create_tournament_and_enqueue

# CLAUDE.md doesn't specify a minimum entrant count for sim rooms (only that
# ranked/unranked need exactly 4) - 2 is the smallest number a round robin is
# even meaningful for. Confirmed (see CLAUDE.md S2), not just a default guess.
MIN_SIM_ROOM_ENTRANTS = 2

_INVITE_CODE_ALPHABET = string.ascii_uppercase + string.digits
_INVITE_CODE_LENGTH = 8


class RoomNotOpenError(Exception):
    pass


class NotRoomOwnerError(Exception):
    pass


class TooFewEntrantsError(Exception):
    pass


class DuplicateEntryError(Exception):
    pass


class DuplicateInviteError(Exception):
    pass


async def _generate_unique_invite_code(db: AsyncSession) -> str:
    for _ in range(10):  # collision is astronomically unlikely; bounded retry defensively
        code = "".join(secrets.choice(_INVITE_CODE_ALPHABET) for _ in range(_INVITE_CODE_LENGTH))
        existing = await db.execute(select(SimRoom.id).where(SimRoom.invite_code == code))
        if existing.scalar_one_or_none() is None:
            return code
    raise RuntimeError("Could not generate a unique invite code.")


async def create_room(db: AsyncSession, *, owner_user_id: uuid.UUID) -> SimRoom:
    code = await _generate_unique_invite_code(db)
    room = SimRoom(owner_user_id=owner_user_id, invite_code=code, status="open")
    db.add(room)
    await db.flush()
    return room


async def join_room(
    db: AsyncSession, *, invite_code: str, user_id: uuid.UUID, automaton_id: uuid.UUID
) -> SimRoomEntry:
    result = await db.execute(select(SimRoom).where(SimRoom.invite_code == invite_code))
    room = result.scalar_one_or_none()
    if room is None or room.status != "open":
        raise RoomNotOpenError("Invite code not found, or the room has already started.")

    existing = await db.execute(
        select(SimRoomEntry.id).where(
            SimRoomEntry.sim_room_id == room.id, SimRoomEntry.automaton_id == automaton_id
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise DuplicateEntryError("This automaton is already entered in this room.")

    entry = SimRoomEntry(sim_room_id=room.id, user_id=user_id, automaton_id=automaton_id)
    db.add(entry)
    await db.flush()
    return entry


async def invite_friend(
    db: AsyncSession, *, room: SimRoom, requesting_user_id: uuid.UUID, invited_user_id: uuid.UUID
) -> SimRoomInvite:
    """Owner-only, and only for an actual friend - re-checked server-side
    rather than trusting the client sent a real friend's id. No realtime
    notification is sent (consistent with Phase 5's no-realtime decision for
    friends) - the invited player finds it via GET /sim-rooms/invites.
    """
    if room.owner_user_id != requesting_user_id:
        raise NotRoomOwnerError("Only the room owner may invite friends.")
    if room.status != "open":
        raise RoomNotOpenError("This room has already started.")
    if not await are_friends(db, user_id=requesting_user_id, other_user_id=invited_user_id):
        raise NotFriendsError("You are not friends with this user.")

    existing = await db.execute(
        select(SimRoomInvite.id).where(
            SimRoomInvite.sim_room_id == room.id, SimRoomInvite.invited_user_id == invited_user_id
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise DuplicateInviteError("This friend has already been invited to this room.")

    invite = SimRoomInvite(
        sim_room_id=room.id, invited_user_id=invited_user_id, invited_by_user_id=requesting_user_id
    )
    db.add(invite)
    await db.flush()
    return invite


async def remove_entry(
    db: AsyncSession, *, room: SimRoom, entry: SimRoomEntry, requesting_user_id: uuid.UUID
) -> None:
    if requesting_user_id not in (room.owner_user_id, entry.user_id):
        raise NotRoomOwnerError("Only the room owner or the entrant may remove an entry.")
    await db.delete(entry)
    await db.flush()


async def leave_room(
    db: AsyncSession, *, room: SimRoom, user_id: uuid.UUID
) -> tuple[bool, uuid.UUID | None]:
    """Removes every one of `user_id`'s own entries from the room (a player
    can have more than one automaton entered). If `user_id` is the room
    owner, ownership is handed to whichever remaining entrant joined
    earliest, or the room is deleted outright if no one else is left -
    handles both an explicit "Leave room" click and an implicit departure
    (the same navigate-away cleanup effect that already removes entries).

    Returns (room_deleted, new_owner_user_id) - the latter is None unless
    ownership actually changed hands.
    """
    own_entries = await db.execute(
        select(SimRoomEntry).where(
            SimRoomEntry.sim_room_id == room.id, SimRoomEntry.user_id == user_id
        )
    )
    for entry in own_entries.scalars().all():
        await db.delete(entry)
    await db.flush()

    if room.owner_user_id != user_id:
        return False, None

    remaining = await db.execute(
        select(SimRoomEntry.user_id)
        .where(SimRoomEntry.sim_room_id == room.id)
        .order_by(SimRoomEntry.created_at)
        .limit(1)
    )
    new_owner_id = remaining.scalar_one_or_none()
    if new_owner_id is None:
        await db.delete(room)
        await db.flush()
        return True, None

    room.owner_user_id = new_owner_id
    await db.flush()
    return False, new_owner_id


async def start_room(
    db: AsyncSession, *, room: SimRoom, requesting_user_id: uuid.UUID
) -> Tournament:
    if room.owner_user_id != requesting_user_id:
        raise NotRoomOwnerError("Only the room owner may start it.")
    if room.status != "open":
        raise RoomNotOpenError("This room has already started.")

    entries_result = await db.execute(
        select(SimRoomEntry).where(SimRoomEntry.sim_room_id == room.id)
    )
    entries = list(entries_result.scalars().all())
    if len(entries) < MIN_SIM_ROOM_ENTRANTS:
        raise TooFewEntrantsError(
            f"At least {MIN_SIM_ROOM_ENTRANTS} entrants are required to start."
        )

    entrant_specs = [(e.user_id, e.automaton_id) for e in entries]
    tournament = await create_tournament_and_enqueue(
        db, tournament_type="sim", entrant_specs=entrant_specs
    )

    room.status = "started"
    room.tournament_id = tournament.id
    await db.flush()
    return tournament
