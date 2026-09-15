from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.auth.dependencies import get_current_user, get_ws_user
from grudge_backend.db import get_db
from grudge_backend.exceptions import not_found
from grudge_backend.models.rating import RatingHistory
from grudge_backend.models.tournament import Tournament
from grudge_backend.models.user import User
from grudge_backend.services.tournaments import list_tournaments_for_user
from grudge_backend.ws import tournament_manager

router = APIRouter(prefix="/tournaments", tags=["tournaments"])
# Deliberately a separate router (no /tournaments prefix) so this can live at
# /me/tournaments, alongside GET /me in routers/auth.py, rather than nested
# under /tournaments/me/tournaments.
me_router = APIRouter(tags=["tournaments"])


class TournamentEntrant(BaseModel):
    user_id: uuid.UUID
    automaton_id: uuid.UUID
    automaton_version_id: uuid.UUID | None
    automaton_name: str | None
    automaton_version_name: str | None
    owner_username: str | None
    rating_snapshot: int
    code_snapshot: str | None
    # Populated only for ranked tournaments, from rating_history - None for
    # unranked/sim (never touch rating) and for a faulted entrant (excluded
    # from the rating update entirely, see services/rating.py).
    rating_delta: float | None = None


class TournamentRead(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    entrants: list[TournamentEntrant]
    result: dict[str, Any] | None
    error_message: str | None


@router.get("/{tournament_id}", response_model=TournamentRead)
async def get_tournament(
    tournament_id: uuid.UUID,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TournamentRead:
    tournament = await db.get(Tournament, tournament_id)
    if tournament is None:
        raise not_found("Tournament not found.")

    delta_by_user_id: dict[str, float] = {}
    if tournament.type == "ranked":
        history_result = await db.execute(
            select(RatingHistory).where(RatingHistory.tournament_id == tournament_id)
        )
        delta_by_user_id = {str(h.user_id): h.delta for h in history_result.scalars().all()}

    entrants = [
        TournamentEntrant(**entrant, rating_delta=delta_by_user_id.get(entrant.get("user_id")))
        for entrant in tournament.entrants
    ]
    return TournamentRead(
        id=tournament.id,
        type=tournament.type,
        status=tournament.status,
        entrants=entrants,
        result=tournament.result,
        error_message=tournament.error_message,
    )


class MyTournamentEntryRead(BaseModel):
    tournament_id: uuid.UUID
    tournament_type: str
    status: str
    created_at: datetime
    automaton_id: uuid.UUID
    automaton_name: str | None
    automaton_version_id: uuid.UUID | None
    automaton_version_name: str | None
    placement: int | None
    voided: bool


@me_router.get("/me/tournaments", response_model=list[MyTournamentEntryRead])
async def my_tournaments(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MyTournamentEntryRead]:
    rows = await list_tournaments_for_user(db, user_id=current_user.id, limit=limit, offset=offset)
    return [
        MyTournamentEntryRead(
            tournament_id=r.tournament_id,
            tournament_type=r.tournament_type,
            status=r.status,
            created_at=r.created_at,
            automaton_id=r.automaton_id,
            automaton_name=r.automaton_name,
            automaton_version_id=r.automaton_version_id,
            automaton_version_name=r.automaton_version_name,
            placement=r.placement,
            voided=r.voided,
        )
        for r in rows
    ]


@router.websocket("/{tournament_id}/ws")
async def tournament_progress_ws(
    websocket: WebSocket, tournament_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    user = await get_ws_user(websocket, db)
    if user is None:
        await websocket.close(code=4401)
        return

    tournament = await db.get(Tournament, tournament_id)
    if tournament is None:
        await websocket.close(code=4401)
        return

    channel = str(tournament_id)
    await tournament_manager.connect(channel, websocket, user.id)
    try:
        while True:
            await (
                websocket.receive_text()
            )  # no client->server messages defined; just keep the socket open
    except WebSocketDisconnect:
        pass
    finally:
        tournament_manager.disconnect(channel, websocket)
