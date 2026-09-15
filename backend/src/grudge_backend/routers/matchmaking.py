from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.auth.dependencies import get_current_user, get_ws_user
from grudge_backend.db import get_db
from grudge_backend.exceptions import bad_request, not_found
from grudge_backend.models.automaton import Automaton
from grudge_backend.models.user import User
from grudge_backend.models.waiting_room import MatchmakingQueueEntry, WaitingRoom
from grudge_backend.services import matchmaking
from grudge_backend.ws import matchmaking_manager

router = APIRouter(prefix="/matchmaking", tags=["matchmaking"])

_QUEUE_TYPES = {"ranked", "unranked"}


class JoinQueueRequest(BaseModel):
    automaton_id: uuid.UUID


class JoinQueueResponse(BaseModel):
    entry_id: uuid.UUID
    room_id: uuid.UUID
    joined_at: str
    tournament_id: uuid.UUID | None = None
    # DB-backed count at the moment of joining, not the (as-yet-unconnected)
    # WS-connection count - lets the client render an accurate status
    # immediately instead of waiting on a count_update broadcast that fires
    # before its own socket has connected (see room_member_count's docstring).
    member_count: int
    capacity: int


@router.post("/{queue_type}/join", response_model=JoinQueueResponse, status_code=201)
async def join_queue(
    queue_type: str,
    payload: JoinQueueRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JoinQueueResponse:
    if queue_type not in _QUEUE_TYPES:
        raise not_found("Unknown queue type.")

    result = await db.execute(
        select(Automaton).where(
            Automaton.id == payload.automaton_id, Automaton.user_id == current_user.id
        )
    )
    automaton = result.scalar_one_or_none()
    if automaton is None:
        raise not_found("Automaton not found.")

    try:
        entry, room, tournament = await matchmaking.join_queue(
            db, user=current_user, automaton=automaton, queue_type=queue_type
        )
    except matchmaking.AlreadyQueuedError as exc:
        await db.rollback()
        raise bad_request(str(exc)) from exc
    except matchmaking.NoActiveVersionError as exc:
        await db.rollback()
        raise bad_request(str(exc)) from exc
    except matchmaking.PreflightFailedError as exc:
        await db.rollback()
        raise bad_request(str(exc)) from exc

    await db.commit()
    await db.refresh(entry)

    # Not a bare 4 - respects Settings.matchmaking_room_capacity_override
    # (test-only, see config.py/TODO.md) so a shrunk-for-testing room reports
    # its real fill target instead of a stale hardcoded number.
    default_size = (
        matchmaking.RANKED_ROOM_SIZE if queue_type == "ranked" else matchmaking.UNRANKED_ROOM_SIZE
    )
    capacity = matchmaking.effective_room_size(default_size)

    channel = str(room.id)
    member_count = await matchmaking.room_member_count(db, room.id)
    if tournament is not None:
        await matchmaking_manager.broadcast(
            channel, {"type": "matched", "data": {"tournament_id": str(tournament.id)}}
        )
    else:
        await matchmaking_manager.broadcast(
            channel,
            {
                "type": "count_update",
                "data": {
                    "room_id": str(room.id),
                    "member_count": member_count,
                    "capacity": capacity,
                },
            },
        )

    return JoinQueueResponse(
        entry_id=entry.id,
        room_id=room.id,
        joined_at=entry.joined_at.isoformat(),
        tournament_id=tournament.id if tournament is not None else None,
        member_count=member_count,
        capacity=capacity,
    )


@router.delete("/queue/{queue_entry_id}", status_code=204)
async def leave_queue(
    queue_entry_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        room_id = await matchmaking.leave_queue(
            db, entry_id=queue_entry_id, user_id=current_user.id
        )
    except matchmaking.QueueEntryNotFoundError as exc:
        raise not_found(str(exc)) from exc
    await db.commit()

    if room_id is not None:
        room = await db.get(WaitingRoom, room_id)
        default_size = (
            matchmaking.RANKED_ROOM_SIZE
            if room is not None and room.room_type == "ranked"
            else matchmaking.UNRANKED_ROOM_SIZE
        )
        capacity = matchmaking.effective_room_size(default_size)
        channel = str(room_id)
        member_count = await matchmaking.room_member_count(db, room_id)
        await matchmaking_manager.broadcast(
            channel,
            {
                "type": "count_update",
                "data": {
                    "room_id": str(room_id),
                    "member_count": member_count,
                    "capacity": capacity,
                },
            },
        )


@router.websocket("/queue/{queue_entry_id}/ws")
async def queue_ws(
    websocket: WebSocket, queue_entry_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    user = await get_ws_user(websocket, db)
    if user is None:
        await websocket.close(code=4401)
        return

    entry = await db.get(MatchmakingQueueEntry, queue_entry_id)
    if entry is None or entry.user_id != user.id:
        await websocket.close(code=4401)
        return

    channel = str(entry.room_id)
    await matchmaking_manager.connect(channel, websocket, user.id)
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "heartbeat":
                await matchmaking.heartbeat(db, entry_id=entry.id)
                await db.commit()
    except WebSocketDisconnect:
        pass
    finally:
        matchmaking_manager.disconnect(channel, websocket)
