from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.auth.dependencies import get_current_user, get_ws_user
from grudge_backend.db import get_db
from grudge_backend.exceptions import bad_request, conflict, forbidden, not_found
from grudge_backend.models.automaton import Automaton
from grudge_backend.models.sim_room import SimRoom, SimRoomEntry, SimRoomInvite
from grudge_backend.models.user import User
from grudge_backend.services import sim_rooms
from grudge_backend.services.friends import NotFriendsError
from grudge_backend.ws import sim_room_manager

router = APIRouter(prefix="/sim-rooms", tags=["sim-rooms"])


class SimRoomRead(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID
    invite_code: str
    status: str


class JoinSimRoomRequest(BaseModel):
    code: str
    automaton_id: uuid.UUID


class SimRoomEntryRead(BaseModel):
    id: uuid.UUID
    sim_room_id: uuid.UUID
    user_id: uuid.UUID
    automaton_id: uuid.UUID
    # Live-joined at read time, not a frozen snapshot (see create_tournament_and_enqueue's
    # docstring for the contrast) - the room hasn't started yet, so showing the
    # current name is correct, not a "later rename rewrites history" risk.
    automaton_name: str
    owner_username: str


class StartSimRoomResponse(BaseModel):
    tournament_id: uuid.UUID


class SimRoomWithEntriesRead(SimRoomRead):
    entries: list[SimRoomEntryRead]


class LeaveSimRoomResponse(BaseModel):
    room_closed: bool
    new_owner_user_id: uuid.UUID | None


class SimRoomInviteRequest(BaseModel):
    friend_user_id: uuid.UUID


class SimRoomInviteRead(BaseModel):
    id: uuid.UUID
    sim_room_id: uuid.UUID
    invite_code: str
    owner_username: str
    invited_at: datetime


async def _get_owned_automaton(
    db: AsyncSession, *, automaton_id: uuid.UUID, user_id: uuid.UUID
) -> Automaton:
    result = await db.execute(
        select(Automaton).where(Automaton.id == automaton_id, Automaton.user_id == user_id)
    )
    automaton = result.scalar_one_or_none()
    if automaton is None:
        raise not_found("Automaton not found.")
    return automaton


async def _entries(db: AsyncSession, room_id: uuid.UUID) -> list[SimRoomEntryRead]:
    result = await db.execute(
        select(SimRoomEntry, Automaton.name, User.username)
        .join(Automaton, Automaton.id == SimRoomEntry.automaton_id)
        .join(User, User.id == SimRoomEntry.user_id)
        .where(SimRoomEntry.sim_room_id == room_id)
    )
    return [
        SimRoomEntryRead(
            id=entry.id,
            sim_room_id=entry.sim_room_id,
            user_id=entry.user_id,
            automaton_id=entry.automaton_id,
            automaton_name=automaton_name,
            owner_username=owner_username,
        )
        for entry, automaton_name, owner_username in result.all()
    ]


def _entries_payload(entries: list[SimRoomEntryRead]) -> list[dict]:
    return [
        {
            "id": str(e.id),
            "sim_room_id": str(e.sim_room_id),
            "user_id": str(e.user_id),
            "automaton_id": str(e.automaton_id),
            "automaton_name": e.automaton_name,
            "owner_username": e.owner_username,
        }
        for e in entries
    ]


@router.post("", response_model=SimRoomRead, status_code=201)
async def create_sim_room(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> SimRoom:
    room = await sim_rooms.create_room(db, owner_user_id=current_user.id)
    await db.commit()
    await db.refresh(room)
    return room


@router.get("/invites", response_model=list[SimRoomInviteRead])
async def list_my_sim_room_invites(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[SimRoomInviteRead]:
    """Registered before the parameterized GET /{room_id} below - a literal
    path must come first or FastAPI would try to parse "invites" as a
    room_id UUID. Only invites for still-`open` rooms are returned - once a
    room starts (or, not currently possible, is cancelled), the invite
    naturally stops being "pending" without needing a status column.
    """
    result = await db.execute(
        select(SimRoomInvite, SimRoom.invite_code, User.username)
        .join(SimRoom, SimRoom.id == SimRoomInvite.sim_room_id)
        .join(User, User.id == SimRoom.owner_user_id)
        .where(SimRoomInvite.invited_user_id == current_user.id, SimRoom.status == "open")
    )
    return [
        SimRoomInviteRead(
            id=invite.id,
            sim_room_id=invite.sim_room_id,
            invite_code=invite_code,
            owner_username=owner_username,
            invited_at=invite.created_at,
        )
        for invite, invite_code, owner_username in result.all()
    ]


@router.post("/{room_id}/invites", response_model=SimRoomInviteRead, status_code=201)
async def invite_friend_to_sim_room(
    room_id: uuid.UUID,
    payload: SimRoomInviteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SimRoomInviteRead:
    room = await db.get(SimRoom, room_id)
    if room is None:
        raise not_found("Room not found.")

    try:
        invite = await sim_rooms.invite_friend(
            db,
            room=room,
            requesting_user_id=current_user.id,
            invited_user_id=payload.friend_user_id,
        )
    except sim_rooms.NotRoomOwnerError as exc:
        await db.rollback()
        raise forbidden(str(exc)) from exc
    except sim_rooms.RoomNotOpenError as exc:
        await db.rollback()
        raise not_found(str(exc)) from exc
    except NotFriendsError as exc:
        await db.rollback()
        raise not_found(str(exc)) from exc
    except sim_rooms.DuplicateInviteError as exc:
        await db.rollback()
        raise conflict(str(exc)) from exc

    await db.commit()
    return SimRoomInviteRead(
        id=invite.id,
        sim_room_id=invite.sim_room_id,
        invite_code=room.invite_code,
        owner_username=current_user.username,
        invited_at=invite.created_at,
    )


@router.get("/{room_id}", response_model=SimRoomWithEntriesRead)
async def get_sim_room(
    room_id: uuid.UUID,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SimRoomWithEntriesRead:
    """Not owner/member-restricted, same reasoning as GET /tournaments/{id}
    (exceptions.forbidden's docstring): sim rooms are shared/invite-code-based
    by design, not a secret per-user resource - lets a page refresh or late
    join hydrate room state instead of waiting on the next WS entries_update.
    """
    room = await db.get(SimRoom, room_id)
    if room is None:
        raise not_found("Room not found.")
    entries = await _entries(db, room_id)
    return SimRoomWithEntriesRead(
        id=room.id,
        owner_user_id=room.owner_user_id,
        invite_code=room.invite_code,
        status=room.status,
        entries=entries,
    )


@router.post("/join", response_model=SimRoomEntryRead, status_code=201)
async def join_sim_room(
    payload: JoinSimRoomRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SimRoomEntryRead:
    await _get_owned_automaton(db, automaton_id=payload.automaton_id, user_id=current_user.id)
    try:
        entry = await sim_rooms.join_room(
            db, invite_code=payload.code, user_id=current_user.id, automaton_id=payload.automaton_id
        )
    except sim_rooms.RoomNotOpenError as exc:
        await db.rollback()
        raise not_found(str(exc)) from exc
    except sim_rooms.DuplicateEntryError as exc:
        await db.rollback()
        raise conflict(str(exc)) from exc

    await db.commit()

    entries = await _entries(db, entry.sim_room_id)
    await sim_room_manager.broadcast(
        str(entry.sim_room_id),
        {
            "type": "entries_update",
            "data": {"entries": _entries_payload(entries), "count": len(entries)},
        },
    )
    return next(e for e in entries if e.id == entry.id)


@router.delete("/{room_id}/entries/{entry_id}", status_code=204)
async def remove_sim_room_entry(
    room_id: uuid.UUID,
    entry_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    room = await db.get(SimRoom, room_id)
    entry = await db.get(SimRoomEntry, entry_id)
    if room is None or entry is None or entry.sim_room_id != room_id:
        raise not_found("Entry not found.")

    try:
        await sim_rooms.remove_entry(db, room=room, entry=entry, requesting_user_id=current_user.id)
    except sim_rooms.NotRoomOwnerError as exc:
        await db.rollback()
        raise forbidden(str(exc)) from exc
    await db.commit()

    entries = await _entries(db, room_id)
    await sim_room_manager.broadcast(
        str(room_id),
        {
            "type": "entries_update",
            "data": {"entries": _entries_payload(entries), "count": len(entries)},
        },
    )


@router.post("/{room_id}/leave", response_model=LeaveSimRoomResponse)
async def leave_sim_room(
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeaveSimRoomResponse:
    """Removes every automaton the caller has entered in this room. If the
    caller is the room owner, ownership is handed to the earliest-joined
    remaining entrant, or the room is deleted outright if no one else is
    left - so an owner leaving/disconnecting never strands the room.
    """
    room = await db.get(SimRoom, room_id)
    if room is None:
        raise not_found("Room not found.")

    room_closed, new_owner_id = await sim_rooms.leave_room(db, room=room, user_id=current_user.id)
    await db.commit()

    if room_closed:
        await sim_room_manager.broadcast(str(room_id), {"type": "room_closed", "data": {}})
        return LeaveSimRoomResponse(room_closed=True, new_owner_user_id=None)

    entries = await _entries(db, room_id)
    await sim_room_manager.broadcast(
        str(room_id),
        {
            "type": "entries_update",
            "data": {"entries": _entries_payload(entries), "count": len(entries)},
        },
    )
    if new_owner_id is not None:
        await sim_room_manager.broadcast(
            str(room_id),
            {"type": "owner_changed", "data": {"owner_user_id": str(new_owner_id)}},
        )
    return LeaveSimRoomResponse(room_closed=False, new_owner_user_id=new_owner_id)


@router.post("/{room_id}/start", response_model=StartSimRoomResponse)
async def start_sim_room(
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StartSimRoomResponse:
    room = await db.get(SimRoom, room_id)
    if room is None:
        raise not_found("Room not found.")

    try:
        tournament = await sim_rooms.start_room(db, room=room, requesting_user_id=current_user.id)
    except sim_rooms.NotRoomOwnerError as exc:
        await db.rollback()
        raise forbidden(str(exc)) from exc
    except sim_rooms.TooFewEntrantsError as exc:
        await db.rollback()
        raise bad_request(str(exc)) from exc

    await db.commit()
    await sim_room_manager.broadcast(
        str(room_id), {"type": "started", "data": {"tournament_id": str(tournament.id)}}
    )
    return StartSimRoomResponse(tournament_id=tournament.id)


@router.websocket("/{room_id}/ws")
async def sim_room_ws(
    websocket: WebSocket, room_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    user = await get_ws_user(websocket, db)
    if user is None:
        await websocket.close(code=4401)
        return

    room = await db.get(SimRoom, room_id)
    if room is None:
        await websocket.close(code=4401)
        return
    entries = await _entries(db, room_id)
    is_member = user.id == room.owner_user_id or any(e.user_id == user.id for e in entries)
    if not is_member:
        await websocket.close(code=4401)
        return

    channel = str(room_id)
    await sim_room_manager.connect(channel, websocket, user.id)
    try:
        while True:
            await (
                websocket.receive_text()
            )  # no client->server messages defined; just keep the socket open
    except WebSocketDisconnect:
        pass
    finally:
        sim_room_manager.disconnect(channel, websocket)
