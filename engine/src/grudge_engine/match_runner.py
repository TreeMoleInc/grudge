"""Runs one match between two automata through a sandbox backend: drives the
randomized-length round loop, enforces per-round/cumulative CPU budgets from the
shim's self-reported cpu_ms (backend-independent - nsjail additionally enforces
its own RLIMIT_CPU as an OS-level backstop on top of this, but match_runner
doesn't need to know or care which backend it's talking to), and produces a
MatchResult that either side of the pipeline (tests now, a future DB-backed
integration layer later) can use to compute scores or void/flag an automaton.
"""

from __future__ import annotations

import random

from grudge_engine.ast_validator import ValidationError, validate
from grudge_engine.automaton import Automaton
from grudge_engine.constants import (
    PER_MATCH_CUMULATIVE_CPU_MS,
    PER_ROUND_CPU_MS,
    SEED_UPPER_BOUND,
    VALID_MOVES,
    WALL_CLOCK_BACKSTOP_S,
)
from grudge_engine.game import payoff
from grudge_engine.length import draw_length
from grudge_engine.protocol import FAULT_TYPES, round_message, shutdown_message
from grudge_engine.results import MatchResult, RoundLogEntry
from grudge_engine.sandbox.base import SandboxBackend, SandboxProcess

_INIT_TIMEOUT_S = WALL_CLOCK_BACKSTOP_S


def run_match(
    automaton_a: Automaton,
    automaton_b: Automaton,
    backend: SandboxBackend,
    *,
    seed: int | None = None,
    length_override: int | None = None,
) -> MatchResult:
    """Run one match between two automata through the given sandbox backend.

    `seed`, when given, makes match length and each side's internal `random`
    module usage exactly reproducible - only ever passed by tests; production
    call sites leave it None for real, unseeded randomness.

    `length_override` skips the geometric length draw and plays exactly that
    many rounds instead - used by preflight.py to run a short fixed-length check
    through this same code path (same limits, "no looser standard" per CLAUDE.md).
    """
    rng = random.Random(seed) if seed is not None else random.Random()
    length = length_override if length_override is not None else draw_length(rng)
    # Distinct per-side seeds derived from the match seed, not the match seed
    # itself, so the two sides' `random` usage doesn't correlate.
    seed_a = rng.randrange(SEED_UPPER_BOUND) if seed is not None else None
    seed_b = rng.randrange(SEED_UPPER_BOUND) if seed is not None else None

    reason_a, reason_b = _validate_or_none(automaton_a), _validate_or_none(automaton_b)
    if reason_a or reason_b:
        return _void_result(
            automaton_a.id,
            automaton_b.id,
            reason_a,
            reason_b,
            games_played=0,
            rounds=(),
            debug_a="",
            debug_b="",
        )

    proc_a = backend.spawn(automaton_a.source, automaton_id=automaton_a.id, seed=seed_a)
    try:
        proc_b = backend.spawn(automaton_b.source, automaton_id=automaton_b.id, seed=seed_b)
    except Exception:
        # Without this, a spawn failure for side b (a transient sandbox error,
        # not automaton_a's fault) leaves proc_a's already-running process and
        # temp source dir orphaned - nothing else in this function ever gets a
        # chance to terminate() it, since the try/finally below hasn't started
        # yet.
        _terminate_quietly(proc_a)
        raise
    try:
        return _drive_match(automaton_a.id, automaton_b.id, proc_a, proc_b, length)
    finally:
        # Each side terminated independently: SandboxProcess.terminate() can
        # itself raise (e.g. an unkillable child - see popen_process.py), and a
        # single `proc_a.terminate(); proc_b.terminate()` would let a raise
        # from the first call skip the second entirely, leaking that side's
        # process/temp dir too.
        _terminate_quietly(proc_a)
        _terminate_quietly(proc_b)


def _terminate_quietly(proc: SandboxProcess) -> None:
    try:
        proc.terminate()
    except Exception:  # noqa: BLE001, S110 - best-effort cleanup; must never mask
        # the real match result/exception this runs alongside, and must never stop
        # a sibling process's own cleanup from running (see callers above). Nothing
        # to log to either - this module has no logging infra of its own.
        pass


def _validate_or_none(automaton: Automaton) -> str | None:
    try:
        validate(automaton.source)
    except (SyntaxError, ValidationError) as exc:
        return str(exc)
    except RecursionError:
        # ast.parse()/the validator's own tree walk can hit Python's recursion
        # limit on pathologically deep-nested-but-syntactically-valid source
        # (e.g. thousands of nested parentheses) - without this, that source
        # crashes run_match (and, via run_tournament's un-isolated match loop,
        # the whole tournament for every other pair) instead of just faulting
        # this one automaton the way any other bad submission does.
        return "Automaton's code is too deeply nested to process."


def _void_result(
    id_a: str,
    id_b: str,
    reason_a: str | None,
    reason_b: str | None,
    *,
    games_played: int,
    rounds: tuple[RoundLogEntry, ...],
    debug_a: str,
    debug_b: str,
    score_a: int = 0,
    score_b: int = 0,
) -> MatchResult:
    voided_side = "both" if (reason_a and reason_b) else ("a" if reason_a else "b")
    # Both reasons are now complete sentences (see _wait_ready/_read_move) -
    # joined with a space, not "; ", so a both-sides fault reads as two plain
    # sentences rather than a semicolon-spliced fragment. This combined string
    # is what the shared Results page shows (see results.py's MatchResult
    # docstring comment) - void_reason_a/void_reason_b below carry the same
    # two reasons kept apart, for a private per-owner channel that must never
    # show one player's fault text to the other.
    reason = " ".join(r for r in (reason_a, reason_b) if r)
    return MatchResult(
        automaton_a_id=id_a,
        automaton_b_id=id_b,
        games_played=games_played,
        score_a=score_a,
        score_b=score_b,
        rounds=rounds,
        status="voided",
        voided_side=voided_side,
        void_reason=reason,
        void_reason_a=reason_a,
        void_reason_b=reason_b,
        debug_log_a=debug_a,
        debug_log_b=debug_b,
    )


def _wait_ready(proc: SandboxProcess) -> str | None:
    """Returned reason string is user-facing (surfaced verbatim in pre-flight
    rejections, durable notifications, and the Results page's voided-match
    rows) and must read as plain language, not internal engine/protocol
    terminology. See CLAUDE.md S2's "professional sentence case" convention,
    extended here to also mean "no engine jargon a player wouldn't recognize"
    (e.g. "pre-flight", round numbers, "CPU budget") - confirmed 2026-08-30.
    """
    msg = proc.read_line(timeout=_INIT_TIMEOUT_S)
    if msg is None:
        return "Automaton timed out during startup."
    msg_type = msg.get("type")
    if msg_type == "ready":
        return None
    if msg_type in FAULT_TYPES:
        return f"Automaton crashed during startup: {msg.get('message', msg.get('error_type', 'unknown error'))}"
    return "Automaton sent an invalid response during startup."


def _read_move(proc: SandboxProcess, round_index: int) -> tuple[str | None, float, str | None]:
    """Returns (move, cpu_ms, fault_reason); move/cpu_ms are None/0.0 on fault.
    `round_index` is used for the round log only - deliberately not embedded
    in `fault_reason` (see `_wait_ready`'s docstring on why these strings stay
    plain-language, no round numbers or protocol jargon).
    """
    msg = proc.read_line(timeout=WALL_CLOCK_BACKSTOP_S)
    if msg is None:
        return None, 0.0, "Automaton timed out."
    msg_type = msg.get("type")
    if msg_type in FAULT_TYPES:
        return (
            None,
            0.0,
            f"Automaton crashed: {msg.get('message', msg.get('error_type', 'unknown error'))}",
        )
    if msg_type != "move":
        return None, 0.0, "Automaton sent an invalid response."
    move = msg.get("move")
    cpu_ms = msg.get("cpu_ms")
    if move not in VALID_MOVES:
        return None, 0.0, "Automaton returned an invalid move."
    # bool is a subclass of int in Python (isinstance(True, int) is True), so
    # it's excluded explicitly - a stray `cpu_ms: true` shouldn't compare as
    # 1ms. The shim always sends a real, non-negative float here (see
    # shim/runtime.py); this only matters if the wire protocol is ever
    # violated (a future shim bug, or a hypothetical sandbox escape writing
    # directly to the process's real stdout) - without it, `cpu_ms > ...`
    # below raises TypeError on a non-numeric value and crashes the whole
    # match instead of just faulting this automaton.
    if not isinstance(cpu_ms, int | float) or isinstance(cpu_ms, bool) or cpu_ms < 0:
        return None, 0.0, "Automaton sent an invalid response."
    if cpu_ms > PER_ROUND_CPU_MS:
        return None, 0.0, "Automaton exceeded its time limit."
    return move, float(cpu_ms), None


def _drive_match(
    id_a: str, id_b: str, proc_a: SandboxProcess, proc_b: SandboxProcess, length: int
) -> MatchResult:
    reason_a = _wait_ready(proc_a)
    reason_b = _wait_ready(proc_b)
    if reason_a or reason_b:
        return _void_result(
            id_a,
            id_b,
            reason_a,
            reason_b,
            games_played=0,
            rounds=(),
            debug_a=proc_a.debug_output(),
            debug_b=proc_b.debug_output(),
        )

    rounds: list[RoundLogEntry] = []
    score_a = 0
    score_b = 0
    cumulative_cpu_a = 0.0
    cumulative_cpu_b = 0.0
    last_move_a: str | None = None
    last_move_b: str | None = None

    for round_index in range(length):
        proc_a.send_line(round_message(round_index, last_move_b))
        proc_b.send_line(round_message(round_index, last_move_a))

        move_a, cpu_a, fault_a = _read_move(proc_a, round_index)
        move_b, cpu_b, fault_b = _read_move(proc_b, round_index)

        if fault_a or fault_b:
            return _void_result(
                id_a,
                id_b,
                fault_a,
                fault_b,
                games_played=round_index,
                rounds=tuple(rounds),
                debug_a=proc_a.debug_output(),
                debug_b=proc_b.debug_output(),
                score_a=score_a,
                score_b=score_b,
            )

        points_a, points_b = payoff(move_a, move_b)
        score_a += points_a
        score_b += points_b
        rounds.append(RoundLogEntry(round_index, move_a, move_b, points_a, points_b))
        last_move_a, last_move_b = move_a, move_b

        cumulative_cpu_a += cpu_a
        cumulative_cpu_b += cpu_b
        if (
            cumulative_cpu_a > PER_MATCH_CUMULATIVE_CPU_MS
            or cumulative_cpu_b > PER_MATCH_CUMULATIVE_CPU_MS
        ):
            over_a = cumulative_cpu_a > PER_MATCH_CUMULATIVE_CPU_MS
            over_b = cumulative_cpu_b > PER_MATCH_CUMULATIVE_CPU_MS
            reason = "Automaton exceeded its total time limit for the match."
            return _void_result(
                id_a,
                id_b,
                reason if over_a else None,
                reason if over_b else None,
                games_played=round_index + 1,
                rounds=tuple(rounds),
                debug_a=proc_a.debug_output(),
                debug_b=proc_b.debug_output(),
                score_a=score_a,
                score_b=score_b,
            )

    proc_a.send_line(shutdown_message())
    proc_b.send_line(shutdown_message())

    return MatchResult(
        automaton_a_id=id_a,
        automaton_b_id=id_b,
        games_played=length,
        score_a=score_a,
        score_b=score_b,
        rounds=tuple(rounds),
        status="completed",
        voided_side=None,
        void_reason=None,
        void_reason_a=None,
        void_reason_b=None,
        debug_log_a=proc_a.debug_output(),
        debug_log_b=proc_b.debug_output(),
    )
