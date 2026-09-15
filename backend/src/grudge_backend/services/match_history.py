"""Relational tournament_entries/matches tables (Phase 6) - an ADDITIVE layer
over tournaments.entrants/result's existing JSONB, populated alongside it in
the same worker transaction, purely so a query like "every match between
these two players" doesn't require scanning JSON. See models/tournament.py's
docstrings for the FK-cascade reasoning (SET NULL, not CASCADE, to mirror
tournaments.entrants's existing account-deletion behavior).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from grudge_engine.results import TournamentResult
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.models.automaton import Automaton
from grudge_backend.models.tournament import Match, Tournament, TournamentEntry
from grudge_backend.models.user import User


def _uuid_or_none(value: str | None) -> uuid.UUID | None:
    return uuid.UUID(value) if value else None


async def record_tournament_result(
    db: AsyncSession, *, tournament: Tournament, result: TournamentResult, entrants: list[dict]
) -> None:
    """Called from worker.py's completion transaction, right after
    `tournament.result = result_to_dict(result)` and before that transaction
    commits - `entrants`/`result` are the same in-scope objects already used
    to build the JSONB blob, not re-fetched.
    """
    for entrant in entrants:
        db.add(
            TournamentEntry(
                tournament_id=tournament.id,
                user_id=_uuid_or_none(entrant.get("user_id")),
                automaton_id=_uuid_or_none(entrant.get("automaton_id")),
                automaton_version_id=_uuid_or_none(entrant.get("automaton_version_id")),
                code_snapshot=entrant.get("code_snapshot"),
                rating_snapshot=entrant["rating_snapshot"],
                automaton_name=entrant.get("automaton_name"),
                owner_username=entrant.get("owner_username"),
                automaton_version_name=entrant.get("automaton_version_name"),
            )
        )

    for match in result.matches:
        db.add(
            Match(
                tournament_id=tournament.id,
                automaton_a_id=_uuid_or_none(match.automaton_a_id),
                automaton_b_id=_uuid_or_none(match.automaton_b_id),
                games_played=match.games_played,
                score_a=match.score_a,
                score_b=match.score_b,
                status=match.status,
                voided_side=match.voided_side,
                void_reason=match.void_reason,
                rounds=[
                    {
                        "round_index": r.round_index,
                        "move_a": r.move_a,
                        "move_b": r.move_b,
                        "points_a": r.points_a,
                        "points_b": r.points_b,
                    }
                    for r in match.rounds
                ],
            )
        )
    await db.flush()


async def head_to_head_matches(
    db: AsyncSession, *, automaton_a_id: uuid.UUID, automaton_b_id: uuid.UUID
) -> list[Match]:
    """Every match between these two automata, oldest first, regardless of
    which side of the pair either one was on in a given match. The proof-of-
    capability query this table exists for - no router/frontend consumer yet,
    see TODO.md.
    """
    stmt = (
        select(Match)
        .where(
            or_(
                (Match.automaton_a_id == automaton_a_id) & (Match.automaton_b_id == automaton_b_id),
                (Match.automaton_a_id == automaton_b_id) & (Match.automaton_b_id == automaton_a_id),
            )
        )
        .order_by(Match.created_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@dataclass(frozen=True)
class AutomatonRecord:
    """An automaton's all-time record across every completed match it has
    played (any tournament type - ranked/unranked/sim all count here, unlike
    rating which is ranked-only). Voided matches (this automaton faulted, or
    its opponent did) are counted separately, not folded into wins/losses -
    a voided match has no real winner.
    """

    automaton_id: uuid.UUID
    matches_played: int
    wins: int
    losses: int
    ties: int
    voided_matches: int
    average_points_per_game: float


async def automaton_record(db: AsyncSession, *, automaton_id: uuid.UUID) -> AutomatonRecord:
    result = await db.execute(
        select(Match).where(
            or_(Match.automaton_a_id == automaton_id, Match.automaton_b_id == automaton_id)
        )
    )
    matches = result.scalars().all()

    wins = losses = ties = voided = 0
    total_points = 0
    total_games = 0
    for match in matches:
        if match.status == "voided":
            voided += 1
            continue
        is_a = match.automaton_a_id == automaton_id
        my_score = match.score_a if is_a else match.score_b
        their_score = match.score_b if is_a else match.score_a
        total_points += my_score
        total_games += match.games_played
        if my_score > their_score:
            wins += 1
        elif my_score < their_score:
            losses += 1
        else:
            ties += 1

    return AutomatonRecord(
        automaton_id=automaton_id,
        matches_played=wins + losses + ties,
        wins=wins,
        losses=losses,
        ties=ties,
        voided_matches=voided,
        average_points_per_game=(total_points / total_games) if total_games else 0.0,
    )


@dataclass(frozen=True)
class HeadToHeadSummary:
    """Same shape of aggregation as AutomatonRecord, but scoped to matches
    against one specific opponent - the actual proof-of-capability use case
    head_to_head_matches was built for. `opponent_name`/`opponent_owner_username`
    are read live from the CURRENT Automaton/User rows (not a tournament-time
    snapshot) - this is a browsing view of "who is this automaton now," not a
    frozen historical record like a Results page's entrants snapshot.
    """

    opponent_automaton_id: uuid.UUID
    opponent_name: str | None
    opponent_owner_username: str | None
    matches: list[Match]
    wins: int
    losses: int
    ties: int
    voided_matches: int


async def head_to_head_summary(
    db: AsyncSession, *, automaton_id: uuid.UUID, opponent_automaton_id: uuid.UUID
) -> HeadToHeadSummary:
    matches = await head_to_head_matches(
        db, automaton_a_id=automaton_id, automaton_b_id=opponent_automaton_id
    )

    opponent_result = await db.execute(
        select(Automaton.name, User.username)
        .join(User, User.id == Automaton.user_id)
        .where(Automaton.id == opponent_automaton_id)
    )
    opponent_row = opponent_result.one_or_none()
    opponent_name = opponent_row[0] if opponent_row else None
    opponent_owner_username = opponent_row[1] if opponent_row else None

    wins = losses = ties = voided = 0
    for match in matches:
        if match.status == "voided":
            voided += 1
            continue
        is_a = match.automaton_a_id == automaton_id
        my_score = match.score_a if is_a else match.score_b
        their_score = match.score_b if is_a else match.score_a
        if my_score > their_score:
            wins += 1
        elif my_score < their_score:
            losses += 1
        else:
            ties += 1

    return HeadToHeadSummary(
        opponent_automaton_id=opponent_automaton_id,
        opponent_name=opponent_name,
        opponent_owner_username=opponent_owner_username,
        matches=matches,
        wins=wins,
        losses=losses,
        ties=ties,
        voided_matches=voided,
    )


@dataclass(frozen=True)
class OpponentSummary:
    """One row per distinct automaton this automaton has ever been matched
    against - what the frontend's stats panel lists to let a player pick who
    to see a head_to_head_summary for, without needing to already know an
    opponent's id.
    """

    opponent_automaton_id: uuid.UUID
    opponent_name: str | None
    opponent_owner_username: str | None
    matches_played: int
    wins: int
    losses: int
    ties: int
    voided_matches: int


async def list_opponents(db: AsyncSession, *, automaton_id: uuid.UUID) -> list[OpponentSummary]:
    result = await db.execute(
        select(Match).where(
            or_(Match.automaton_a_id == automaton_id, Match.automaton_b_id == automaton_id)
        )
    )
    matches = result.scalars().all()

    by_opponent: dict[uuid.UUID, list[Match]] = {}
    for match in matches:
        is_a = match.automaton_a_id == automaton_id
        opponent_id = match.automaton_b_id if is_a else match.automaton_a_id
        if opponent_id is None:
            # The opponent automaton has since been deleted (SET NULL) -
            # nothing left to link to or show a name for.
            continue
        by_opponent.setdefault(opponent_id, []).append(match)

    if not by_opponent:
        return []

    names_result = await db.execute(
        select(Automaton.id, Automaton.name, User.username)
        .join(User, User.id == Automaton.user_id)
        .where(Automaton.id.in_(by_opponent.keys()))
    )
    names_by_id = {row[0]: (row[1], row[2]) for row in names_result.all()}

    summaries = []
    for opponent_id, opponent_matches in by_opponent.items():
        wins = losses = ties = voided = 0
        for match in opponent_matches:
            if match.status == "voided":
                voided += 1
                continue
            is_a = match.automaton_a_id == automaton_id
            my_score = match.score_a if is_a else match.score_b
            their_score = match.score_b if is_a else match.score_a
            if my_score > their_score:
                wins += 1
            elif my_score < their_score:
                losses += 1
            else:
                ties += 1
        name, username = names_by_id.get(opponent_id, (None, None))
        summaries.append(
            OpponentSummary(
                opponent_automaton_id=opponent_id,
                opponent_name=name,
                opponent_owner_username=username,
                matches_played=wins + losses + ties,
                wins=wins,
                losses=losses,
                ties=ties,
                voided_matches=voided,
            )
        )

    # Most-played opponent first - the one a player is most likely to want to
    # drill into.
    summaries.sort(key=lambda s: s.matches_played, reverse=True)
    return summaries
