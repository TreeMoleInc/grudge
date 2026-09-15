"""Axelrod-classic reference bots, kept as real automaton source files (using the
actual public decide(history) API/constants) rather than internal-only test
fixtures - this doubles as validation of the API design itself. Exposed here as
source-text strings for use by match_runner/tournament_runner/preflight and
tests, which need the raw source (to run through the real sandboxed AST-
validated path) rather than an importable Python object.
"""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (_DIR / name).read_text(encoding="utf-8")


TIT_FOR_TAT_SOURCE = _read("tit_for_tat.py")
ALWAYS_COOPERATE_SOURCE = _read("always_cooperate.py")
ALWAYS_DEFECT_SOURCE = _read("always_defect.py")
GRUDGER_SOURCE = _read("grudger.py")
RANDOM_BOT_SOURCE = _read("random_bot.py")
