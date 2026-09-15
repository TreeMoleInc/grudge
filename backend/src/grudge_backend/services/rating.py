"""Elo rating-update math (CLAUDE.md S2 - E_i/S_i/K-tiers/zero-sum delta_i,
fully specified there, implemented here for the first time in Phase 6). Only
`tournament.type == "ranked"` ever calls into this - unranked/sim never touch
rating.

Pure functions first (k_factor, compute_rating_updates), mirroring
services/matchmaking.py's window_radius/group_is_compatible precedent - no
DB/async dependency, fully unit-testable. apply_rating_update is the thin
async DB-touching wrapper, exercised only via integration tests.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from grudge_engine.results import TournamentResult
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.models.rating import RatingHistory
from grudge_backend.models.tournament import Tournament
from grudge_backend.models.user import User

K_PROVISIONAL = 32
K_STANDARD = 20
K_ELITE = 10
PROVISIONAL_TOURNAMENTS_THRESHOLD = 30
ELITE_RATING_THRESHOLD = 1800


@dataclass(frozen=True)
class RatingInput:
    user_id: str
    rating: int
    ranked_tournaments_played: int
    points_per_game: float


@dataclass(frozen=True)
class RatingUpdate:
    user_id: str
    rating_before: int
    new_rating: int
    delta: float
    k_used: int
    e_i: float
    s_i: float
    ranked_tournaments_played_before: int


def k_factor(*, ranked_tournaments_played: int, rating: int) -> int:
    """Checked in this priority order (CLAUDE.md S2) - provisional overrides
    the rating-based tiers even for a high rating reached quickly."""
    if ranked_tournaments_played < PROVISIONAL_TOURNAMENTS_THRESHOLD:
        return K_PROVISIONAL
    if rating < ELITE_RATING_THRESHOLD:
        return K_STANDARD
    return K_ELITE


def compute_rating_updates(entrants: list[RatingInput]) -> list[RatingUpdate] | None:
    """Assumes each user_id appears at most once - guaranteed by ranked
    matchmaking's one-active-queue-entry-per-user invariant. Returns None if
    every r_i is 0 (S_i undefined, CLAUDE.md's stated edge case) or fewer than
    2 entrants remain (E_i's n*(n-1) divisor undefined - an extension of the
    same edge case for when enough automata faulted that only 0-1 survive).
    """
    n = len(entrants)
    if n < 2:
        return None
    total_r = sum(e.points_per_game for e in entrants)
    if total_r == 0:
        return None

    k_by_user = {
        e.user_id: k_factor(ranked_tournaments_played=e.ranked_tournaments_played, rating=e.rating)
        for e in entrants
    }
    s_by_user = {e.user_id: e.points_per_game / total_r for e in entrants}
    e_by_user = {}
    for i in entrants:
        total = sum(
            1 / (1 + 10 ** ((j.rating - i.rating) / 400))
            for j in entrants
            if j.user_id != i.user_id
        )
        e_by_user[i.user_id] = (2 / (n * (n - 1))) * total

    raw_delta_by_user = {
        e.user_id: k_by_user[e.user_id] * (s_by_user[e.user_id] - e_by_user[e.user_id])
        for e in entrants
    }
    # Zero-sum correction (CLAUDE.md S2): the same scalar for every entrant,
    # so subtracting it from each raw delta makes the deltas sum to exactly 0
    # even though K varies per player.
    correction = sum(raw_delta_by_user.values()) / n

    updates = []
    for e in entrants:
        delta = raw_delta_by_user[e.user_id] - correction
        updates.append(
            RatingUpdate(
                user_id=e.user_id,
                rating_before=e.rating,
                new_rating=round(e.rating + delta),
                delta=delta,
                k_used=k_by_user[e.user_id],
                e_i=e_by_user[e.user_id],
                s_i=s_by_user[e.user_id],
                ranked_tournaments_played_before=e.ranked_tournaments_played,
            )
        )
    return updates


async def apply_rating_update(
    db: AsyncSession, *, tournament: Tournament, result: TournamentResult, entrants: list[dict]
) -> list[RatingUpdate] | None:
    """Called from worker.py's completion transaction, only when
    tournament.type == "ranked". `result.standings` already excludes faulted
    automata (the engine's own doing, not re-derived here) - a faulted
    automaton's owner is skipped from both the rating-update roster AND every
    other player's E_i/S_i computation, as if never in the tournament for
    rating purposes. ranked_tournaments_played still increments for every
    non-faulted entrant regardless of whether compute_rating_updates ends up
    skipping the actual rating change (CLAUDE.md's "the player still played
    it" assumption).
    """
    points_per_game_by_automaton = {s.automaton_id: s.points_per_game for s in result.standings}
    entrant_by_automaton = {e["automaton_id"]: e for e in entrants}

    users_by_id: dict[uuid.UUID, User] = {}
    rating_inputs: list[RatingInput] = []
    for automaton_id, points_per_game in points_per_game_by_automaton.items():
        entrant = entrant_by_automaton.get(automaton_id)
        if entrant is None or entrant.get("user_id") is None:
            continue
        user_id = uuid.UUID(entrant["user_id"])
        user = await db.get(User, user_id)
        if user is None:
            continue
        user.ranked_tournaments_played += 1
        users_by_id[user_id] = user
        rating_inputs.append(
            RatingInput(
                user_id=str(user_id),
                rating=user.rating,
                ranked_tournaments_played=user.ranked_tournaments_played - 1,  # pre-increment value
                points_per_game=points_per_game,
            )
        )

    updates = compute_rating_updates(rating_inputs)
    if updates is None:
        return None

    for update in updates:
        user = users_by_id[uuid.UUID(update.user_id)]
        user.rating = update.new_rating
        db.add(
            RatingHistory(
                tournament_id=tournament.id,
                user_id=user.id,
                rating_before=update.rating_before,
                rating_after=update.new_rating,
                delta=update.delta,
                k_used=update.k_used,
                e_i=update.e_i,
                s_i=update.s_i,
                ranked_tournaments_played_before=update.ranked_tournaments_played_before,
            )
        )
    await db.flush()
    return updates
