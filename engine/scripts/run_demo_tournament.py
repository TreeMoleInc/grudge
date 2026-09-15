"""Manual smoke test / demo: run one seeded 8-automaton round robin through
the reference bots (plus two extra Axelrod-flavored variants) and print
standings. Deliberately not tied to the product's live ranked/unranked room
size (currently 4, see CLAUDE.md S2/backend/services/matchmaking.py) - the
engine itself is N-generic, and a bigger field makes for a more interesting
demo. Not part of the automated test suite - a quick way to eyeball sane
output beyond just assertions.

Run from the engine/ directory (with the package importable, e.g. after
`pip install -e .[dev]`):

    python scripts/run_demo_tournament.py
"""

from __future__ import annotations

import warnings

from grudge_engine.automaton import Automaton
from grudge_engine.reference_bots import (
    ALWAYS_COOPERATE_SOURCE,
    ALWAYS_DEFECT_SOURCE,
    GRUDGER_SOURCE,
    RANDOM_BOT_SOURCE,
    TIT_FOR_TAT_SOURCE,
)
from grudge_engine.sandbox.dev_backend import DevSandboxBackend
from grudge_engine.tournament_runner import run_tournament

# Two extra Axelrod-flavored variants beyond the core reference_bots set, just to
# fill out a bigger 8-automaton field for this demo (see the module docstring
# on why this doesn't mirror the product's actual room size).
SUSPICIOUS_TFT_SOURCE = (
    "def decide(history):\n"
    "    if not history:\n"
    "        return DEFECT\n"
    "    return history[-1].opponent\n"
)

TIT_FOR_TWO_TATS_SOURCE = (
    "def decide(history):\n"
    "    if len(history) < 2:\n"
    "        return COOPERATE\n"
    "    if history[-1].opponent == DEFECT and history[-2].opponent == DEFECT:\n"
    "        return DEFECT\n"
    "    return COOPERATE\n"
)

AUTOMATA = [
    Automaton(id="tit_for_tat", source=TIT_FOR_TAT_SOURCE),
    Automaton(id="always_cooperate", source=ALWAYS_COOPERATE_SOURCE),
    Automaton(id="always_defect", source=ALWAYS_DEFECT_SOURCE),
    Automaton(id="grudger", source=GRUDGER_SOURCE),
    Automaton(id="random", source=RANDOM_BOT_SOURCE),
    Automaton(id="suspicious_tft", source=SUSPICIOUS_TFT_SOURCE),
    Automaton(id="tit_for_two_tats", source=TIT_FOR_TWO_TATS_SOURCE),
    Automaton(id="random_2", source=RANDOM_BOT_SOURCE),
]


def main() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # DevSandboxBackend's insecure-use warning
        backend = DevSandboxBackend()

    result = run_tournament(AUTOMATA, backend, seed=2026)

    print(f"Ran {len(result.matches)} matches among {len(AUTOMATA)} automata.\n")

    if result.faulted:
        print("Faulted automata:")
        for f in result.faulted:
            print(f"  {f.automaton_id}: {f.reason}")
        print()

    print(f"{'Rank':<5}{'Automaton':<20}{'Pts/Game':<10}{'Games':<8}")
    for rank, standing in enumerate(result.standings, start=1):
        print(
            f"{rank:<5}{standing.automaton_id:<20}"
            f"{standing.points_per_game:<10.3f}{standing.total_games:<8}"
        )


if __name__ == "__main__":
    main()
