"""Input type: one automaton entry (id + source code), as passed into
match_runner / tournament_runner / preflight. Kept separate from results.py,
which holds output types only.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Automaton:
    id: str
    source: str
