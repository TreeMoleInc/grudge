"""N-generic round robin: every pair in the given automata list plays exactly
once (n*(n-1)/2 matches for n automata - e.g. 6 matches for the product's
current 4-player ranked/unranked room size, but this function has no opinion
on n; that fixed size lives in backend/services/matchmaking.py, not here -
see the non-8-automata test in test_tournament_runner.py), aggregated into
standings. Per CLAUDE.md's voiding rules, a faulted automaton is removed from
the tournament entirely and ALL of its matches - including ones that had
already completed cleanly - are voided for both participants; the tournament
otherwise continues for everyone else.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Callable

from grudge_engine.automaton import Automaton
from grudge_engine.constants import SEED_UPPER_BOUND
from grudge_engine.match_runner import run_match
from grudge_engine.results import FaultedEntry, MatchResult, StandingEntry, TournamentResult
from grudge_engine.sandbox.base import SandboxBackend


def _voided_ids(match: MatchResult) -> tuple[str, ...]:
    if match.status != "voided" or match.voided_side is None:
        return ()
    if match.voided_side == "both":
        return (match.automaton_a_id, match.automaton_b_id)
    if match.voided_side == "a":
        return (match.automaton_a_id,)
    return (match.automaton_b_id,)


def _reason_for(match: MatchResult, automaton_id: str) -> str:
    """The private, per-owner reason for `automaton_id`'s own fault in `match` -
    deliberately NOT `match.void_reason` (the combined string shown on the
    shared Results page), which reads like this automaton's own reason but, in
    the both-sides-faulted case, is actually both automatons' fault text
    joined together. Using it here would leak the other player's private
    crash/timeout detail (potentially their own raised exception's message)
    into this automaton's owner-only notification and stats page - added
    2026-09-14 after review surfaced this as a real cross-player leak, not
    just a display nit.
    """
    own_reason = (
        match.void_reason_a if automaton_id == match.automaton_a_id else match.void_reason_b
    )
    return own_reason or match.void_reason or "Automaton was voided due to a related failure."


def run_tournament(
    automata: list[Automaton],
    backend: SandboxBackend,
    *,
    seed: int | None = None,
    length_override: int | None = None,
    on_match_complete: Callable[[MatchResult, int, int], None] | None = None,
) -> TournamentResult:
    """`seed`, when given, makes the whole tournament (match order is already
    deterministic - fixed sort by id - and every match's own randomness) exactly
    reproducible; production call sites leave it None.

    `length_override`, when given, is forwarded to every match instead of each
    drawing its own randomized length - production call sites never pass this
    (every real match still draws its own independent random length); it exists
    so tests can compare aggregate points-per-game across automata without
    per-match length variance dominating the comparison (a match that happens to
    draw a much longer length than another otherwise skews the game-count-
    weighted aggregate, independent of actual strategy strength).

    `on_match_complete`, when given, is called synchronously after each match
    finishes with (that match's MatchResult, matches_completed_so_far,
    total_matches) - purely a progress-reporting hook (e.g. a caller pushing
    "3/6 done" over a websocket); it does not affect scoring/voiding and any
    exception it raises propagates immediately, aborting the tournament. Optional
    and defaults to None so existing callers are unaffected.
    """
    ordered = sorted(automata, key=lambda a: a.id)
    top_rng = random.Random(seed) if seed is not None else None
    pairs = list(itertools.combinations(ordered, 2))
    total_matches = len(pairs)

    matches: list[MatchResult] = []
    for a, b in pairs:
        match_seed = top_rng.randrange(SEED_UPPER_BOUND) if top_rng is not None else None
        result = run_match(a, b, backend, seed=match_seed, length_override=length_override)
        matches.append(result)
        if on_match_complete is not None:
            on_match_complete(result, len(matches), total_matches)

    faulted_reasons: dict[str, list[str]] = {}
    for match in matches:
        for automaton_id in _voided_ids(match):
            faulted_reasons.setdefault(automaton_id, []).append(_reason_for(match, automaton_id))

    faulted_entries = tuple(
        FaultedEntry(
            automaton_id=automaton_id,
            # Deduplicated (not just joined) - the same automaton commonly
            # fails the same way (e.g. "Automaton crashed: ValueError: boom")
            # across every match it plays once its code is broken, and
            # repeating an identical sentence per opponent reads as noise,
            # not new information. dict.fromkeys preserves first-seen order.
            reason=" ".join(dict.fromkeys(reasons)),
            voided_match_ids=tuple(
                m.participant_ids() for m in matches if automaton_id in m.participant_ids()
            ),
        )
        for automaton_id, reasons in faulted_reasons.items()
    )

    totals: dict[str, list[int]] = {a.id: [0, 0] for a in ordered}  # id -> [points, games]
    for match in matches:
        if match.automaton_a_id in faulted_reasons or match.automaton_b_id in faulted_reasons:
            continue  # voided "for everyone involved", even if this specific match was clean
        totals[match.automaton_a_id][0] += match.score_a
        totals[match.automaton_a_id][1] += match.games_played
        totals[match.automaton_b_id][0] += match.score_b
        totals[match.automaton_b_id][1] += match.games_played

    standings = sorted(
        (
            StandingEntry(automaton_id=automaton_id, total_points=points, total_games=games)
            for automaton_id, (points, games) in totals.items()
            if automaton_id not in faulted_reasons
        ),
        key=lambda s: s.points_per_game,
        reverse=True,
    )

    return TournamentResult(
        automaton_ids=tuple(a.id for a in ordered),
        matches=tuple(matches),
        standings=tuple(standings),
        faulted=faulted_entries,
    )
