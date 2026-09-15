"""Pre-flight check: run a candidate automaton through a short, fixed-length match
against the fixed Random reference bot, through the exact same sandbox path and
limits as a real match ("no looser standard", per CLAUDE.md). Random is used
specifically because it has no exploitable pattern, so it can't accidentally mask
broken decision logic the way a simple fixed-pattern opponent could.

Actually blocking entry into a live tournament based on this result is a later
(Phase 6) integration concern - this module just provides the reusable
run-and-report capability.
"""

from __future__ import annotations

from grudge_engine.automaton import Automaton
from grudge_engine.constants import PREFLIGHT_NUM_GAMES
from grudge_engine.match_runner import run_match
from grudge_engine.reference_bots import RANDOM_BOT_SOURCE
from grudge_engine.results import PreflightResult
from grudge_engine.sandbox.base import SandboxBackend

_PREFLIGHT_OPPONENT_ID = "__preflight_random__"


def run_preflight(
    automaton: Automaton,
    backend: SandboxBackend,
    *,
    num_games: int = PREFLIGHT_NUM_GAMES,
    seed: int | None = None,
) -> PreflightResult:
    opponent = Automaton(id=_PREFLIGHT_OPPONENT_ID, source=RANDOM_BOT_SOURCE)
    result = run_match(automaton, opponent, backend, seed=seed, length_override=num_games)

    if result.status == "completed":
        return PreflightResult(passed=True, games_played=result.games_played)

    candidate_failed = result.voided_side in ("a", "both")
    # The candidate is always automaton_a (the positional order passed to
    # run_match above) - void_reason_a, not the combined void_reason, so a
    # both-sides fault (the reference Random opponent faulting too, a rare
    # harness-side flake) never tells the candidate their code did something
    # it didn't, by way of the opponent's unrelated fault text mixed in.
    return PreflightResult(
        passed=not candidate_failed,
        games_played=result.games_played,
        reason=result.void_reason_a if candidate_failed else None,
    )
