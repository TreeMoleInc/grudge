"""The stdin/stdout wire protocol between the harness (match_runner, running in the
parent process) and an automaton's shim (shim/runtime.py, running inside the
sandboxed child process).

One JSON object per line, harness -> child on stdin, child -> harness on stdout.
Player `print()` output is captured on stderr instead (see shim/runtime.py) and
never touches this stream.

The harness sends only the *delta* each round (the opponent's previous move), not
the full history — the shim reconstructs `history` itself. This keeps the wire
format tiny and means the shim never learns the total match length.
"""

from __future__ import annotations

import json
from typing import Any

PROTOCOL_VERSION = 1


def round_message(round_index: int, opponent_last_move: str | None) -> dict[str, Any]:
    return {
        "v": PROTOCOL_VERSION,
        "type": "round",
        "round_index": round_index,
        "opponent_last_move": opponent_last_move,
    }


def shutdown_message() -> dict[str, Any]:
    return {"v": PROTOCOL_VERSION, "type": "shutdown"}


def ready_message() -> dict[str, Any]:
    return {"v": PROTOCOL_VERSION, "type": "ready"}


def move_message(round_index: int, move: str, cpu_ms: float) -> dict[str, Any]:
    return {
        "v": PROTOCOL_VERSION,
        "type": "move",
        "round_index": round_index,
        "move": move,
        "cpu_ms": cpu_ms,
    }


def fatal_error_message(
    phase: str, error_type: str, message: str, round_index: int | None = None
) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "v": PROTOCOL_VERSION,
        "type": "fatal_error",
        "phase": phase,
        "error_type": error_type,
        "message": message,
    }
    if round_index is not None:
        msg["round_index"] = round_index
    return msg


def protocol_error_message(message: str) -> dict[str, Any]:
    """Synthesized by the harness's reader thread (never sent by the child) when a
    line can't be parsed as JSON at all, or EOF is hit. Lets match_runner treat
    every kind of fault uniformly.
    """
    return {"v": PROTOCOL_VERSION, "type": "protocol_error", "message": message}


FAULT_TYPES = frozenset({"fatal_error", "protocol_error"})


def encode_line(msg: dict[str, Any]) -> str:
    return json.dumps(msg, separators=(",", ":"))


def decode_line(line: str) -> dict[str, Any]:
    """May raise json.JSONDecodeError / ValueError on malformed input — callers on
    the harness side should catch and convert to a protocol_error_message.
    """
    return json.loads(line)
