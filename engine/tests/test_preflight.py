from grudge_engine import preflight as preflight_module
from grudge_engine.automaton import Automaton
from grudge_engine.constants import PREFLIGHT_NUM_GAMES
from grudge_engine.preflight import run_preflight
from grudge_engine.reference_bots import TIT_FOR_TAT_SOURCE
from grudge_engine.results import MatchResult

BROKEN_SOURCE = "def decide(history):\n    raise ValueError('boom')\n"
MISSING_DECIDE_SOURCE = "x = 1\n"
DISALLOWED_IMPORT_SOURCE = "import os\ndef decide(history):\n    return COOPERATE\n"


def test_healthy_automaton_passes_preflight(backend):
    tft = Automaton(id="tft", source=TIT_FOR_TAT_SOURCE)
    result = run_preflight(tft, backend, seed=1)
    assert result.passed is True
    assert result.games_played == PREFLIGHT_NUM_GAMES
    assert result.reason is None


def test_broken_automaton_fails_preflight(backend):
    broken = Automaton(id="broken", source=BROKEN_SOURCE)
    result = run_preflight(broken, backend, seed=1)
    assert result.passed is False
    assert result.reason is not None


def test_missing_decide_fails_preflight(backend):
    broken = Automaton(id="broken", source=MISSING_DECIDE_SOURCE)
    result = run_preflight(broken, backend, seed=1)
    assert result.passed is False


def test_ast_invalid_automaton_fails_preflight(backend):
    broken = Automaton(id="broken", source=DISALLOWED_IMPORT_SOURCE)
    result = run_preflight(broken, backend, seed=1)
    assert result.passed is False


def test_preflight_num_games_is_respected(backend):
    tft = Automaton(id="tft", source=TIT_FOR_TAT_SOURCE)
    result = run_preflight(tft, backend, num_games=3, seed=1)
    assert result.games_played == 3


def test_preflight_never_surfaces_the_reference_bots_own_fault_text(monkeypatch, backend):
    # 2026-09-14 fix: if the fixed Random reference opponent ever faults in the
    # same round the candidate does (voided_side == "both", a rare harness-side
    # flake), the candidate's rejection reason must be their own fault only -
    # never the reference bot's unrelated fault text mixed in.
    def fake_run_match(automaton_a, automaton_b, backend, *, seed=None, length_override=None):
        return MatchResult(
            automaton_a_id=automaton_a.id,
            automaton_b_id=automaton_b.id,
            games_played=0,
            score_a=0,
            score_b=0,
            rounds=(),
            status="voided",
            voided_side="both",
            void_reason="Candidate's own reason. Reference bot's own reason.",
            void_reason_a="Candidate's own reason.",
            void_reason_b="Reference bot's own reason.",
            debug_log_a="",
            debug_log_b="",
        )

    monkeypatch.setattr(preflight_module, "run_match", fake_run_match)
    tft = Automaton(id="tft", source=TIT_FOR_TAT_SOURCE)
    result = run_preflight(tft, backend, seed=1)
    assert result.passed is False
    assert result.reason == "Candidate's own reason."
    assert "Reference bot's own reason" not in result.reason
