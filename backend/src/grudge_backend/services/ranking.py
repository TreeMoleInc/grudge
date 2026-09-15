"""Tie-aware placement for tournament standings - standard competition ranking
(1, 1, 3, not dense 1, 1, 2): automata with exactly equal points_per_game share
a placement, and the next distinct score skips ahead by the number tied.
Mirrored in the frontend by `frontend/src/lib/ranking.ts` for the same
StandingsTable display, since the two can't share code across the JS/Python
boundary.
"""

from __future__ import annotations


def rank_with_ties(standings: list[dict]) -> dict[str, int]:
    """`standings` must already be sorted descending by points_per_game (the
    engine guarantees this - see grudge_engine.results.TournamentResult).
    """
    ranks: dict[str, int] = {}
    for index, entry in enumerate(standings):
        if index > 0 and entry["points_per_game"] == standings[index - 1]["points_per_game"]:
            ranks[entry["automaton_id"]] = ranks[standings[index - 1]["automaton_id"]]
        else:
            ranks[entry["automaton_id"]] = index + 1
    return ranks
