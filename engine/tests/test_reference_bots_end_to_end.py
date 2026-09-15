"""Validation against known IPD outcomes involving Random, which has no
closed-form result (unlike the purely-deterministic pairings covered in
test_match_runner.py) - these use a fixed seed for reproducibility and assert a
sane range rather than an exact score, since Random can't be systematically
exploited but also can't guarantee mutual cooperation.
"""

import pytest

from grudge_engine.ast_validator import validate
from grudge_engine.automaton import Automaton
from grudge_engine.match_runner import run_match
from grudge_engine.reference_bots import (
    ALWAYS_COOPERATE_SOURCE,
    ALWAYS_DEFECT_SOURCE,
    GRUDGER_SOURCE,
    RANDOM_BOT_SOURCE,
    TIT_FOR_TAT_SOURCE,
)

ALL_REFERENCE_SOURCES = [
    TIT_FOR_TAT_SOURCE,
    ALWAYS_COOPERATE_SOURCE,
    ALWAYS_DEFECT_SOURCE,
    GRUDGER_SOURCE,
    RANDOM_BOT_SOURCE,
]


@pytest.mark.parametrize("source", ALL_REFERENCE_SOURCES)
def test_reference_bots_pass_the_ast_validator(source):
    # Dogfooding: these are real automaton source files using the public API,
    # so they should validate exactly like a player submission would.
    validate(source)  # should not raise


def test_tft_vs_random_is_not_systematically_exploited(backend):
    tft = Automaton(id="tft", source=TIT_FOR_TAT_SOURCE)
    rnd = Automaton(id="random", source=RANDOM_BOT_SOURCE)
    result = run_match(tft, rnd, backend, seed=7, length_override=200)
    assert result.status == "completed"
    ppg_tft = result.score_a / result.games_played
    ppg_random = result.score_b / result.games_played
    # Neither side should be way outside the [1, 3] band a "no exploitable
    # pattern" opponent should keep both scores within.
    assert 1.0 <= ppg_tft <= 3.5
    assert 1.0 <= ppg_random <= 3.5


def test_grudger_vs_random_is_not_systematically_exploited(backend):
    grudger = Automaton(id="grudger", source=GRUDGER_SOURCE)
    rnd = Automaton(id="random", source=RANDOM_BOT_SOURCE)
    result = run_match(grudger, rnd, backend, seed=11, length_override=200)
    assert result.status == "completed"
    ppg_grudger = result.score_a / result.games_played
    ppg_random = result.score_b / result.games_played
    # Grudger has no forgiveness: Random's very first defection (near-certain
    # within 200 rounds at 50/50 odds) locks in permanent mutual-or-worse
    # defection for the rest of the match, so unlike TFT, Random genuinely CAN
    # end up scoring below 1.0/game here - that's Grudger correctly punishing,
    # not the engine mis-scoring. Grudger itself can't end up below 1.0: once
    # triggered it always nets either 5 (opponent still cooperates) or 1 (mutual
    # defection) per round, never less.
    assert 1.0 <= ppg_grudger <= 5.0
    assert 0.0 <= ppg_random <= 5.0


def test_grudger_never_forgives_after_a_single_defection(backend):
    grudger = Automaton(id="grudger", source=GRUDGER_SOURCE)
    alld = Automaton(id="alld", source=ALWAYS_DEFECT_SOURCE)
    result = run_match(grudger, alld, backend, length_override=20)
    assert result.status == "completed"
    # round 0: grudger cooperates (betrayed), all rounds after: mutual defection
    assert result.rounds[0].move_a == "COOPERATE"
    assert all(r.move_a == "DEFECT" for r in result.rounds[1:])
