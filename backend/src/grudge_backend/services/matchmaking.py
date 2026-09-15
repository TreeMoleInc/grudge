"""Ranked (expanding-window, spread-bounded, no-fixed-anchor) and unranked
(no rating constraint) waiting-room matchmaking. See CLAUDE.md S2 for the
product design; this module implements it plus the small additions logged in
TODO.md (heartbeat eviction extended to ranked, a starvation-backstop sweep).

The window/spread functions are pure and take `elapsed_seconds`/`now` as
explicit arguments rather than reading a clock internally - mirrors
grudge_engine's injected-`seed` determinism philosophy, and is what makes
tests/unit/test_matchmaking.py possible without real sleeps.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.config import settings
from grudge_backend.models.automaton import Automaton, AutomatonVersion
from grudge_backend.models.tournament import Tournament
from grudge_backend.models.user import User
from grudge_backend.models.waiting_room import MatchmakingQueueEntry, WaitingRoom
from grudge_backend.services.preflight import (
    NoActiveVersionError,
    PreflightFailedError,
    run_preflight_check,
)
from grudge_backend.services.tournaments import create_tournament_and_enqueue

RANKED_ROOM_SIZE = 4
UNRANKED_ROOM_SIZE = 4


def effective_room_size(default_size: int) -> int:
    """Applies Settings.matchmaking_room_capacity_override (test-only, see
    config.py) if set, else returns the real 4-player size unchanged. Fails
    loudly on an obviously-invalid override rather than silently ignoring it -
    same philosophy as worker.py's sandbox-backend selection.
    """
    override = settings.matchmaking_room_capacity_override
    if override is None:
        return default_size
    if override < 2:
        raise ValueError(
            f"MATCHMAKING_ROOM_CAPACITY_OVERRIDE={override!r} is invalid - must be >= 2."
        )
    return override


WINDOW_START = 100
WINDOW_STEP = 50
WINDOW_STEP_SECONDS = 15
WINDOW_DROP_SECONDS = 120

HEARTBEAT_STALE_SECONDS = 30


def window_radius(elapsed_seconds: float) -> int | None:
    """None means the constraint has dropped entirely - past this point ANY
    match beats indefinite waiting (CLAUDE.md S2). This IS the sole
    anti-indefinite-wait mechanism for ranked; no separate hard timeout.
    """
    if elapsed_seconds >= WINDOW_DROP_SECONDS:
        return None
    return WINDOW_START + WINDOW_STEP * int(elapsed_seconds // WINDOW_STEP_SECONDS)


def group_is_compatible(radii: list[int | None], spread: int) -> bool:
    """A group (existing room members + a candidate, or two rooms being tested
    for a merge) is valid iff its rating spread fits inside the MOST
    restrictive currently-active member's radius - CLAUDE.md: "stays within
    the tightest currently-active window among all of them". Each player's
    radius already IS their full tolerance (|delta| <= radius for a pairwise
    fit), so this is spread <= min(active radii), not 2x that - see the Phase
    3 plan's explicit note correcting an earlier draft that got this wrong.
    """
    active = [r for r in radii if r is not None]
    if not active:
        return True  # everyone's constraint has dropped - any match beats waiting
    return spread <= min(active)


def room_accepts(
    existing_radii: list[int | None], candidate_radius: int | None, spread: int
) -> bool:
    """Join-time convenience wrapper over group_is_compatible for the common
    "existing members + one new candidate" case.
    """
    return group_is_compatible([*existing_radii, candidate_radius], spread)


def is_stale(
    last_heartbeat_at: datetime, now: datetime, threshold_seconds: float = HEARTBEAT_STALE_SECONDS
) -> bool:
    return (now - last_heartbeat_at).total_seconds() > threshold_seconds


class AlreadyQueuedError(Exception):
    pass


async def _room_members(db: AsyncSession, room_id: uuid.UUID) -> list[MatchmakingQueueEntry]:
    result = await db.execute(
        select(MatchmakingQueueEntry).where(
            MatchmakingQueueEntry.room_id == room_id, MatchmakingQueueEntry.status == "waiting"
        )
    )
    return list(result.scalars().all())


async def room_member_count(db: AsyncSession, room_id: uuid.UUID) -> int:
    """The DB-backed count of `waiting` entries in a room - NOT the same as
    `ws.ConnectionManager.member_count`, which only counts currently-open
    WebSocket connections. A joiner's own connection isn't open yet at the
    moment their join HTTP response is built (the WS connects only after
    React re-renders with the new entry_id), so a WS-connection-based count
    at that instant undercounts by at least the joiner themself - the caller
    needs this DB-backed count instead for anything returned synchronously
    from the join/leave HTTP handlers.
    """
    return len(await _room_members(db, room_id))


async def _maybe_start_room(
    db: AsyncSession, room: WaitingRoom, *, capacity: int
) -> Tournament | None:
    # Row-locked re-fetch, not the `room` object passed in: under Postgres's
    # default READ COMMITTED isolation, two concurrent join_queue calls
    # landing in the same room would otherwise each see the *same*
    # pre-join-request member snapshot from their own transaction, each
    # independently conclude "capacity reached," and each create its own
    # Tournament from an overlapping entrant list - double-booking the
    # existing members into two concurrent tournaments at once. SELECT ...
    # FOR UPDATE here blocks a second concurrent call on this same room until
    # the first commits, so by the time it proceeds it sees the first call's
    # now-committed members (including whether the room already started) and
    # `sweep_ranked_starvation`'s merges share this protection too, since
    # they also route through this same function - see CLAUDE.md's 2026-09-15
    # deploy-readiness review entry.
    locked = await db.execute(
        select(WaitingRoom).where(WaitingRoom.id == room.id).with_for_update()
    )
    locked_room = locked.scalar_one_or_none()
    if locked_room is None or locked_room.status != "open":
        return None

    members = await _room_members(db, locked_room.id)
    if len(members) < capacity:
        return None

    entrant_specs = [(m.user_id, m.automaton_id) for m in members]
    tournament = await create_tournament_and_enqueue(
        db, tournament_type=locked_room.room_type, entrant_specs=entrant_specs
    )
    for m in members:
        m.status = "matched"
    locked_room.status = "started"
    locked_room.tournament_id = tournament.id
    await db.flush()
    return tournament


async def _find_ranked_room(
    db: AsyncSession, *, candidate_rating: int, now: datetime
) -> WaitingRoom | None:
    """Closest-to-full qualifying room, per CLAUDE.md: "preferring the
    closest-to-full qualifying room, to get tournaments starting sooner".
    """
    rooms_result = await db.execute(
        select(WaitingRoom).where(WaitingRoom.room_type == "ranked", WaitingRoom.status == "open")
    )
    open_rooms = list(rooms_result.scalars().all())

    best: tuple[int, WaitingRoom] | None = None
    for room in open_rooms:
        members = await _room_members(db, room.id)
        if not members:
            continue
        ratings = [m.rating_snapshot for m in members] + [candidate_rating]
        spread = max(ratings) - min(ratings)
        existing_radii = [window_radius((now - m.joined_at).total_seconds()) for m in members]
        candidate_radius = window_radius(0.0)  # a fresh join always starts at full radius
        if room_accepts(existing_radii, candidate_radius, spread) and (
            best is None or len(members) > best[0]
        ):
            best = (len(members), room)
    return best[1] if best is not None else None


async def join_queue(
    db: AsyncSession,
    *,
    user: User,
    automaton: Automaton,
    queue_type: str,
    now: datetime | None = None,
) -> tuple[MatchmakingQueueEntry, WaitingRoom, Tournament | None]:
    """Evaluated once, at join time, per CLAUDE.md - a join either lands in an
    existing qualifying room or seeds a new one; already-matched players are
    never re-validated later, since windows only ever widen over time.

    Takes the already-loaded, already-ownership-checked `Automaton` ORM row
    (the router loads it for that check anyway) rather than just an id, since
    Phase 6's pre-flight gate below needs its `active_version_id`/code too.
    """
    now = now or datetime.now(UTC)

    existing = await db.execute(
        select(MatchmakingQueueEntry).where(
            MatchmakingQueueEntry.user_id == user.id, MatchmakingQueueEntry.status == "waiting"
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise AlreadyQueuedError("You already have an active queue entry.")

    # Pre-flight runs fresh, synchronously, on every join (no caching/staleness
    # column on automaton_versions - CLAUDE.md's literal "runs before... enters
    # a live tournament" wording, confirmed as the simpler choice over caching).
    # Runs before any row is written below, so a failure needs no rollback of
    # partial state. Sim rooms are NOT gated by this - only this queue-join path.
    if automaton.active_version_id is None:
        raise NoActiveVersionError("This automaton has no active version to enter with.")
    version = await db.get(AutomatonVersion, automaton.active_version_id)
    preflight_result = await asyncio.to_thread(
        run_preflight_check, automaton_id=str(automaton.id), code=version.code
    )
    if not preflight_result.passed:
        raise PreflightFailedError(preflight_result.reason)

    entry = MatchmakingQueueEntry(
        user_id=user.id,
        automaton_id=automaton.id,
        queue_type=queue_type,
        rating_snapshot=user.rating,
        joined_at=now,
        last_heartbeat_at=now,
        status="waiting",
    )
    db.add(entry)
    try:
        await db.flush()
    except IntegrityError as exc:
        # The SELECT check above isn't atomic with this INSERT - two
        # near-simultaneous join requests for the same user (a double-click,
        # or a retry) can both pass it before either commits. The DB's own
        # partial unique index (uq_matchmaking_queue_entries_one_active_per_
        # user) correctly stops the duplicate row; without this catch, the
        # loser surfaced as an unhandled 500 instead of the same friendly
        # "already queued" error the first check produces.
        raise AlreadyQueuedError("You already have an active queue entry.") from exc

    if queue_type == "unranked":
        capacity = effective_room_size(UNRANKED_ROOM_SIZE)
        room_result = await db.execute(
            select(WaitingRoom).where(
                WaitingRoom.room_type == "unranked", WaitingRoom.status == "open"
            )
        )
        room = None
        for candidate in room_result.scalars().all():
            if len(await _room_members(db, candidate.id)) < capacity:
                room = candidate
                break
    else:
        room = await _find_ranked_room(db, candidate_rating=user.rating, now=now)
        capacity = effective_room_size(RANKED_ROOM_SIZE)

    if room is None:
        room = WaitingRoom(room_type=queue_type, status="open")
        db.add(room)
        await db.flush()

    entry.room_id = room.id
    await db.flush()

    tournament = await _maybe_start_room(db, room, capacity=capacity)
    return entry, room, tournament


async def heartbeat(db: AsyncSession, *, entry_id: uuid.UUID, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    entry = await db.get(MatchmakingQueueEntry, entry_id)
    if entry is not None and entry.status == "waiting":
        entry.last_heartbeat_at = now
        await db.flush()


class QueueEntryNotFoundError(Exception):
    pass


async def leave_queue(
    db: AsyncSession, *, entry_id: uuid.UUID, user_id: uuid.UUID
) -> uuid.UUID | None:
    """Voluntary leave, the explicit counterpart to the stale-heartbeat sweep
    above - lets a "cancel" click take effect immediately instead of the player
    being stuck unable to rejoin for up to HEARTBEAT_STALE_SECONDS. Returns the
    entry's room_id (if it had one) so the caller can push an updated
    count_update; raises if the entry doesn't exist, isn't the caller's own, or
    has already left the "waiting" state (already matched/evicted - nothing to do).
    """
    entry = await db.get(MatchmakingQueueEntry, entry_id)
    if entry is None or entry.user_id != user_id or entry.status != "waiting":
        raise QueueEntryNotFoundError("No active queue entry with that ID was found for you.")
    entry.status = "evicted"
    room_id = entry.room_id
    await db.flush()
    return room_id


async def sweep_stale_entries(db: AsyncSession, *, now: datetime | None = None) -> set[uuid.UUID]:
    """Evicts queue entries whose heartbeat has gone stale (both ranked and
    unranked - see TODO.md). Returns the set of affected room_ids so callers
    can push updated count_update messages.
    """
    now = now or datetime.now(UTC)
    result = await db.execute(
        select(MatchmakingQueueEntry).where(MatchmakingQueueEntry.status == "waiting")
    )
    affected_rooms: set[uuid.UUID] = set()
    for entry in result.scalars().all():
        if is_stale(entry.last_heartbeat_at, now):
            entry.status = "evicted"
            if entry.room_id is not None:
                affected_rooms.add(entry.room_id)
    await db.flush()
    return affected_rooms


async def sweep_ranked_starvation(
    db: AsyncSession, *, now: datetime | None = None
) -> list[tuple[Tournament, uuid.UUID]]:
    """Backstop for a gap in pure join-time evaluation: two already-waiting,
    mutually-incompatible entries can never be re-matched if no third player
    ever joins, even after both cross the 120s unconstrained mark. Periodically
    (same cadence as the watchdog) attempts pairwise room merges; a real
    addition beyond the literal CLAUDE.md spec text, logged in TODO.md.

    Returns (tournament, room_id) pairs for each tournament started this way,
    so a caller can push a "matched" WS event to that room's channel.
    """
    now = now or datetime.now(UTC)
    capacity = effective_room_size(RANKED_ROOM_SIZE)
    rooms_result = await db.execute(
        select(WaitingRoom)
        .where(WaitingRoom.room_type == "ranked", WaitingRoom.status == "open")
        .order_by(WaitingRoom.created_at)
    )
    rooms = list(rooms_result.scalars().all())
    started: list[tuple[Tournament, uuid.UUID]] = []

    for i, room_a in enumerate(rooms):
        if room_a.status != "open":
            continue
        members_a = await _room_members(db, room_a.id)
        if not members_a:
            continue
        for room_b in rooms[i + 1 :]:
            if room_b.status != "open":
                continue
            members_b = await _room_members(db, room_b.id)
            if not members_b or len(members_a) + len(members_b) > capacity:
                continue

            combined = members_a + members_b
            ratings = [m.rating_snapshot for m in combined]
            spread = max(ratings) - min(ratings)
            radii = [window_radius((now - m.joined_at).total_seconds()) for m in combined]
            if not group_is_compatible(radii, spread):
                continue

            for m in members_b:
                m.room_id = room_a.id
            room_b.status = "merged"
            await db.flush()

            tournament = await _maybe_start_room(db, room_a, capacity=capacity)
            if tournament is not None:
                started.append((tournament, room_a.id))
                break  # room_a is gone (started) - move to the next room_a candidate
            members_a = await _room_members(db, room_a.id)

    return started
