"""Result data structures shared across match_runner / tournament_runner / preflight.
Kept in their own module to avoid import cycles between those three.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoundLogEntry:
    round_index: int
    move_a: str
    move_b: str
    points_a: int
    points_b: int


@dataclass(frozen=True)
class MatchResult:
    automaton_a_id: str
    automaton_b_id: str
    games_played: int
    score_a: int
    score_b: int
    rounds: tuple[RoundLogEntry, ...]
    status: str  # "completed" | "voided"
    voided_side: str | None  # "a" | "b" | "both" | None (which side(s) faulted)
    # Combined, display-ready string (e.g. "Automaton A: <reason>. Automaton B:
    # <reason>." when both faulted) - what the shared Results page shows for
    # this match, per CLAUDE.md S2's "surfaced verbatim... on the Results
    # page's voided-match rows". void_reason_a/void_reason_b below are the same
    # information kept per-side, specifically so a PRIVATE, per-owner channel
    # (a fault notification, an automaton's own stats page) can show only that
    # owner's own automaton's reason - never blending in the other side's fault
    # text the way reading this combined field for both owners would. Added
    # 2026-09-14: tournament_runner.py previously had no per-side field to read
    # and used this combined one for both owners' private notifications too.
    void_reason: str | None
    void_reason_a: str | None
    void_reason_b: str | None
    debug_log_a: str
    debug_log_b: str

    def participant_ids(self) -> tuple[str, str]:
        return (self.automaton_a_id, self.automaton_b_id)


@dataclass(frozen=True)
class StandingEntry:
    automaton_id: str
    total_points: int
    total_games: int

    @property
    def points_per_game(self) -> float:
        return self.total_points / self.total_games if self.total_games else 0.0


@dataclass(frozen=True)
class FaultedEntry:
    automaton_id: str
    reason: str
    voided_match_ids: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class TournamentResult:
    automaton_ids: tuple[str, ...]
    matches: tuple[MatchResult, ...]
    standings: tuple[StandingEntry, ...]  # sorted descending by points_per_game
    faulted: tuple[FaultedEntry, ...]


@dataclass(frozen=True)
class PreflightResult:
    passed: bool
    games_played: int
    reason: str | None = None
