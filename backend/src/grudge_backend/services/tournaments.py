"""Shared "start a tournament" logic used by both ranked/unranked room-fill
(services/matchmaking.py) and sim-room start (services/sim_rooms.py): snapshot
each entrant's code + rating, create a thin Tournament row, and enqueue the
job that actually runs it. See services/match_history.py (Phase 6) for the
relational tournament_entries/matches tables populated alongside this JSONB
snapshot once the tournament actually completes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.models.automaton import Automaton, AutomatonVersion
from grudge_backend.models.job import Job
from grudge_backend.models.tournament import Tournament
from grudge_backend.models.user import User
from grudge_backend.services.ranking import rank_with_ties


async def create_tournament_and_enqueue(
    db: AsyncSession,
    *,
    tournament_type: str,
    entrant_specs: list[tuple[uuid.UUID, uuid.UUID]],  # [(user_id, automaton_id), ...]
    seed: int | None = None,
) -> Tournament:
    """`entrant_specs` must already be validated by the caller (ownership, no
    duplicates, room/room capacity correct) - this function trusts its input.
    """
    entrants = []
    for user_id, automaton_id in entrant_specs:
        automaton = await db.get(Automaton, automaton_id)
        user = await db.get(User, user_id)
        version = (
            await db.get(AutomatonVersion, automaton.active_version_id)
            if automaton.active_version_id is not None
            else None
        )
        entrants.append(
            {
                "user_id": str(user_id),
                "automaton_id": str(automaton_id),
                "automaton_version_id": str(automaton.active_version_id)
                if automaton.active_version_id
                else None,
                "code_snapshot": version.code if version is not None else None,
                "rating_snapshot": user.rating,
                # Captured here, not read live from automata/users/versions at
                # display time - a later rename shouldn't retroactively rewrite a
                # past results page, same immutable-snapshot reasoning as
                # code_snapshot above.
                "automaton_name": automaton.name,
                "owner_username": user.username,
                "automaton_version_name": version.name if version is not None else None,
            }
        )

    tournament = Tournament(type=tournament_type, status="pending", entrants=entrants, seed=seed)
    db.add(tournament)
    await db.flush()

    db.add(
        Job(
            job_type="tournament",
            status="queued",
            payload={"tournament_id": str(tournament.id)},
        )
    )
    await db.flush()

    return tournament


@dataclass(frozen=True)
class MyTournamentEntry:
    """One row in a player's tournament history: one of THEIR OWN entrants within
    one tournament (a sim room could plausibly enter the same user's automaton
    twice, though not ranked/unranked - one row per participation either way, not
    one row per tournament, so that case renders sanely rather than being
    silently collapsed).
    """

    tournament_id: uuid.UUID
    tournament_type: str
    status: str
    created_at: object  # datetime, left loose here to avoid importing it just for a type hint
    automaton_id: uuid.UUID
    automaton_name: str | None
    automaton_version_id: uuid.UUID | None
    automaton_version_name: str | None
    placement: int | None  # 1-based rank among non-voided standings; None if N/A
    voided: bool


def _placement_for(automaton_id: str, result: dict | None) -> tuple[int | None, bool]:
    if result is None:
        return None, False
    faulted_ids = {f["automaton_id"] for f in result.get("faulted", [])}
    if automaton_id in faulted_ids:
        return None, True
    standings = result.get("standings", [])
    ranks = rank_with_ties(standings)
    if automaton_id in ranks:
        return ranks[automaton_id], False
    return None, False


async def list_tournaments_for_user(
    db: AsyncSession, *, user_id: uuid.UUID, limit: int = 50, offset: int = 0
) -> list[MyTournamentEntry]:
    """Paginated by tournament (not by row) - `limit`/`offset` apply to the
    underlying tournament query, ordered newest-first; a tournament with >1 of
    the user's own entrants still expands to >1 row in the result, so the
    returned list can be slightly longer than `limit` in that edge case.
    """
    stmt = (
        select(Tournament)
        .where(Tournament.entrants.op("@>")(cast([{"user_id": str(user_id)}], JSONB)))
        .order_by(Tournament.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    tournaments = result.scalars().all()

    rows: list[MyTournamentEntry] = []
    for tournament in tournaments:
        for entrant in tournament.entrants:
            if entrant["user_id"] != str(user_id):
                continue
            placement, voided = _placement_for(entrant["automaton_id"], tournament.result)
            rows.append(
                MyTournamentEntry(
                    tournament_id=tournament.id,
                    tournament_type=tournament.type,
                    status=tournament.status,
                    created_at=tournament.created_at,
                    automaton_id=uuid.UUID(entrant["automaton_id"]),
                    automaton_name=entrant.get("automaton_name"),
                    automaton_version_id=(
                        uuid.UUID(entrant["automaton_version_id"])
                        if entrant.get("automaton_version_id")
                        else None
                    ),
                    automaton_version_name=entrant.get("automaton_version_name"),
                    placement=placement,
                    voided=voided,
                )
            )
    return rows
