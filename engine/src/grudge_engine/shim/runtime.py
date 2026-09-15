"""Trusted entry point that runs *inside* the sandboxed child process, one per
automaton per match. Invoked as `python -m grudge_engine.shim.runtime <source_path>`.

Everything in this module is trusted, shim-side code — it is never exec'd through
the restricted builtins and player code never gets a reference to any of its
names, since player code only ever sees the fresh globals dict built in
_build_player_globals(). That asymmetry (shim state lives in this module's/
main()'s own scope, never written into player_globals) is the actual isolation
boundary between "the harness's own bookkeeping" and "what an automaton can touch."

Protocol: stdin/stdout carry the JSON-lines wire protocol (protocol.py). Player
`print()` output is redirected to stderr instead, so it can never corrupt the
protocol stream (see restricted_builtins.build_restricted_builtins).
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
import traceback

from grudge_engine import ast_validator, protocol
from grudge_engine.constants import COOPERATE, DEFECT, VALID_MOVES, C, D
from grudge_engine.game import Round
from grudge_engine.restricted_builtins import build_restricted_builtins


def _debug_print(*args: object, **kwargs: object) -> None:
    kwargs.setdefault("file", sys.stderr)
    kwargs.setdefault("flush", True)
    print(*args, **kwargs)


def _emit(msg: dict) -> None:
    sys.stdout.write(protocol.encode_line(msg) + "\n")
    sys.stdout.flush()


def _exc_message(exc: BaseException) -> str:
    return "".join(traceback.format_exception_only(type(exc), exc)).strip()


def _build_player_globals() -> dict:
    return {
        "__builtins__": build_restricted_builtins(_debug_print),
        "COOPERATE": COOPERATE,
        "DEFECT": DEFECT,
        "C": C,
        "D": D,
    }


def main() -> None:
    if len(sys.argv) != 2:
        _emit(
            protocol.fatal_error_message(
                "init", "UsageError", "expected exactly one argument: path to automaton source"
            )
        )
        sys.exit(1)

    source_path = sys.argv[1]

    # Optional deterministic seeding for tests (see match_runner.py) - never set
    # in production, where each process seeds from real OS entropy as usual.
    seed_env = os.environ.get("GRUDGE_SEED")
    if seed_env is not None:
        random.seed(int(seed_env))

    try:
        with open(source_path, encoding="utf-8") as f:
            source = f.read()
    except OSError as exc:
        _emit(protocol.fatal_error_message("init", type(exc).__name__, str(exc)))
        sys.exit(1)

    # Second AST validation pass, inside the child, on top of match_runner's own
    # pre-spawn check - defense in depth against any future code path that could
    # reach this point without going through the parent-side check.
    try:
        ast_validator.validate(source)
    except (SyntaxError, ast_validator.ValidationError) as exc:
        _emit(protocol.fatal_error_message("init", type(exc).__name__, str(exc)))
        sys.exit(1)

    player_globals = _build_player_globals()
    try:
        compiled = compile(source, "<automaton>", "exec")
        exec(compiled, player_globals)  # noqa: S102 - the whole point of this module
    except Exception as exc:  # noqa: BLE001 - must catch any player-raised exception
        _emit(protocol.fatal_error_message("init", type(exc).__name__, _exc_message(exc)))
        sys.exit(1)

    decide = player_globals.get("decide")
    if not callable(decide):
        _emit(
            protocol.fatal_error_message(
                "init",
                "MissingDecideError",
                "automaton does not define a callable decide(history) function",
            )
        )
        sys.exit(1)

    _emit(protocol.ready_message())

    history: list[Round] = []
    last_own_move: str | None = None

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            # The harness itself is trusted; a malformed line here means
            # something is badly wrong upstream. Nothing useful to do but exit.
            sys.exit(1)

        msg_type = msg.get("type")
        if msg_type == "shutdown":
            break
        if msg_type != "round":
            continue

        round_index = msg["round_index"]
        opponent_last_move = msg.get("opponent_last_move")

        if round_index > 0:
            history.append(Round(me=last_own_move, opponent=opponent_last_move))

        start = time.process_time()
        try:
            move = decide(history)
        except Exception as exc:  # noqa: BLE001 - must catch any player-raised exception
            _emit(
                protocol.fatal_error_message(
                    "round", type(exc).__name__, _exc_message(exc), round_index=round_index
                )
            )
            sys.exit(1)
        cpu_ms = (time.process_time() - start) * 1000.0

        # decide() returning a syntactically-valid-but-wrong value (e.g. True, or
        # "Cooperate") is NOT caught by NameError the way a typo'd constant name
        # would be - it has to be checked explicitly here.
        if move not in VALID_MOVES:
            _emit(
                protocol.fatal_error_message(
                    "round",
                    "InvalidMoveError",
                    f"decide() returned {move!r}, expected COOPERATE or DEFECT",
                    round_index=round_index,
                )
            )
            sys.exit(1)

        last_own_move = move
        _emit(protocol.move_message(round_index, move, cpu_ms))


if __name__ == "__main__":
    main()
