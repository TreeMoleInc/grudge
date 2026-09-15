"""match_runner tests split in two styles:

- Fault-injection tests against a scripted fake SandboxProcess (no real
  subprocess, no real timing) - the only practical way to deterministically
  trigger the per-round/cumulative CPU-budget paths without flaky wall-clock-
  dependent busy loops.
- Real-backend tests (via the `backend` fixture / DevSandboxBackend) for the
  pre-spawn AST-validation path and the shim's own init-time fault path, and for
  end-to-end score correctness against deterministic reference bots.
"""

from __future__ import annotations

from grudge_engine import match_runner
from grudge_engine.automaton import Automaton
from grudge_engine.constants import PER_MATCH_CUMULATIVE_CPU_MS
from grudge_engine.protocol import move_message, ready_message
from grudge_engine.reference_bots import (
    ALWAYS_COOPERATE_SOURCE,
    ALWAYS_DEFECT_SOURCE,
    GRUDGER_SOURCE,
    TIT_FOR_TAT_SOURCE,
)


class _ScriptedProcess:
    """Duck-types just enough of SandboxProcess for match_runner - not a real
    subclass since match_runner never isinstance()-checks it.
    """

    def __init__(self, messages: list[dict]) -> None:
        self._messages = list(messages)
        self.sent: list[dict] = []

    def send_line(self, msg: dict) -> None:
        self.sent.append(msg)

    def read_line(self, timeout: float) -> dict | None:
        if not self._messages:
            return None
        return self._messages.pop(0)

    def poll(self) -> int | None:
        return None

    def terminate(self) -> None:
        pass

    def debug_output(self) -> str:
        return ""


# -- fault injection via scripted fakes -------------------------------------------


def test_per_round_cpu_limit_voids_offending_side():
    proc_a = _ScriptedProcess([ready_message(), move_message(0, "COOPERATE", 300.0)])  # over 250ms
    proc_b = _ScriptedProcess([ready_message(), move_message(0, "COOPERATE", 1.0)])
    result = match_runner._drive_match("a", "b", proc_a, proc_b, length=5)
    assert result.status == "voided"
    assert result.voided_side == "a"
    assert result.games_played == 0


def test_both_sides_over_per_round_limit_voids_both():
    proc_a = _ScriptedProcess([ready_message(), move_message(0, "COOPERATE", 300.0)])
    proc_b = _ScriptedProcess([ready_message(), move_message(0, "COOPERATE", 300.0)])
    result = match_runner._drive_match("a", "b", proc_a, proc_b, length=5)
    assert result.voided_side == "both"


def test_both_sides_faulting_differently_keeps_reasons_separate_per_side():
    # 2026-09-14 fix: previously both automatons' fault text was joined into
    # the single void_reason field and that combined string was used verbatim
    # as EACH side's own private fault reason - one player's owner would see
    # the other player's crash detail. void_reason_a/void_reason_b must each
    # carry only that side's own text.
    proc_a = _ScriptedProcess([ready_message()])  # times out
    proc_b = _ScriptedProcess(
        [ready_message(), {"type": "fatal_error", "phase": "round", "message": "boom from B"}]
    )
    result = match_runner._drive_match("a", "b", proc_a, proc_b, length=5)
    assert result.voided_side == "both"
    assert "timed out" in result.void_reason_a
    assert "boom from B" not in result.void_reason_a
    assert "boom from B" in result.void_reason_b
    assert "timed out" not in result.void_reason_b
    # The combined field (shown on the shared Results page) still carries both.
    assert "timed out" in result.void_reason
    assert "boom from B" in result.void_reason


def test_invalid_cpu_ms_faults_the_automaton_instead_of_crashing():
    # A malformed move message (cpu_ms missing/null/non-numeric/negative) must
    # be treated as a fault, not raise a TypeError that would crash the whole
    # match (and, via run_tournament, every other pair in the tournament).
    for bad_cpu_ms in (None, "not-a-number", -1.0, True):
        msg = {"v": 1, "type": "move", "round_index": 0, "move": "COOPERATE"}
        if bad_cpu_ms is not None:
            msg["cpu_ms"] = bad_cpu_ms
        proc_a = _ScriptedProcess([ready_message(), msg])
        proc_b = _ScriptedProcess([ready_message(), move_message(0, "COOPERATE", 1.0)])
        result = match_runner._drive_match("a", "b", proc_a, proc_b, length=5)
        assert result.status == "voided", f"cpu_ms={bad_cpu_ms!r} should have faulted"
        assert result.voided_side == "a"


def test_deeply_nested_source_faults_instead_of_crashing_validation(backend):
    # A RecursionError from ast.parse()/the validator's own traversal on
    # pathologically nested-but-syntactically-valid source must fault just
    # this automaton, not propagate and abort the whole run.
    nested = "def decide(history):\n    return " + "(" * 5000 + "COOPERATE" + ")" * 5000 + "\n"
    broken = Automaton(id="broken", source=nested)
    tft = Automaton(id="tft", source=TIT_FOR_TAT_SOURCE)
    result = match_runner.run_match(broken, tft, backend, length_override=5)
    assert result.status == "voided"
    assert result.voided_side == "a"
    assert result.games_played == 0


def test_second_spawn_failure_still_terminates_the_first_process():
    class _FailingBackend:
        def __init__(self, first_proc):
            self._first_proc = first_proc
            self._calls = 0

        def spawn(self, source_code, *, automaton_id, seed=None):
            self._calls += 1
            if self._calls == 1:
                return self._first_proc
            raise RuntimeError("transient sandbox spawn failure")

    proc_a = _ScriptedProcess([ready_message()])
    terminated = []
    proc_a.terminate = lambda: terminated.append("a")
    backend = _FailingBackend(proc_a)
    a = Automaton(id="a", source=ALWAYS_COOPERATE_SOURCE)
    b = Automaton(id="b", source=ALWAYS_COOPERATE_SOURCE)
    try:
        match_runner.run_match(a, b, backend, length_override=1)
        raised = False
    except RuntimeError:
        raised = True
    assert raised, "the second spawn's failure should propagate, not be swallowed"
    assert terminated == ["a"], "the first process must still be terminated/cleaned up"


def test_timeout_waiting_for_move_voids_that_side():
    proc_a = _ScriptedProcess([ready_message()])  # no move message queued -> read_line returns None
    proc_b = _ScriptedProcess([ready_message(), move_message(0, "COOPERATE", 1.0)])
    result = match_runner._drive_match("a", "b", proc_a, proc_b, length=5)
    assert result.status == "voided"
    assert result.voided_side == "a"
    assert "timed out" in result.void_reason


def test_cumulative_cpu_budget_voids_after_many_rounds():
    per_round_cpu = 200.0  # under the 250ms per-round cap, but adds up over time
    rounds_needed = int(PER_MATCH_CUMULATIVE_CPU_MS / per_round_cpu) + 2
    messages_a = [ready_message()] + [
        move_message(i, "COOPERATE", per_round_cpu) for i in range(rounds_needed)
    ]
    messages_b = [ready_message()] + [
        move_message(i, "COOPERATE", 1.0) for i in range(rounds_needed)
    ]
    proc_a = _ScriptedProcess(messages_a)
    proc_b = _ScriptedProcess(messages_b)
    result = match_runner._drive_match("a", "b", proc_a, proc_b, length=rounds_needed)
    assert result.status == "voided"
    assert result.voided_side == "a"
    assert result.void_reason == "Automaton exceeded its total time limit for the match."
    assert result.games_played > 0  # rounds before the breach still count/scored


def test_completed_match_reports_status_completed():
    proc_a = _ScriptedProcess([ready_message(), move_message(0, "COOPERATE", 1.0)])
    proc_b = _ScriptedProcess([ready_message(), move_message(0, "DEFECT", 1.0)])
    result = match_runner._drive_match("a", "b", proc_a, proc_b, length=1)
    assert result.status == "completed"
    assert result.voided_side is None
    assert result.score_a == 0  # C vs D
    assert result.score_b == 5


# -- real backend: pre-spawn / init-time fault paths ------------------------------


def test_ast_invalid_source_is_voided_before_ever_spawning(backend):
    broken = Automaton(
        id="broken", source="import os\ndef decide(history):\n    return COOPERATE\n"
    )
    tft = Automaton(id="tft", source=TIT_FOR_TAT_SOURCE)
    result = match_runner.run_match(broken, tft, backend, length_override=5)
    assert result.status == "voided"
    assert result.voided_side == "a"
    assert result.games_played == 0


def test_missing_decide_is_voided_at_init(backend):
    broken = Automaton(id="broken", source="x = 1\n")
    tft = Automaton(id="tft", source=TIT_FOR_TAT_SOURCE)
    result = match_runner.run_match(tft, broken, backend, length_override=5)
    assert result.status == "voided"
    assert result.voided_side == "b"


# -- real backend: exact deterministic outcomes against reference bots -----------


def test_tft_vs_always_cooperate_is_mutual_cooperation(backend):
    tft = Automaton(id="tft", source=TIT_FOR_TAT_SOURCE)
    allc = Automaton(id="allc", source=ALWAYS_COOPERATE_SOURCE)
    result = match_runner.run_match(tft, allc, backend, length_override=5)
    assert result.status == "completed"
    assert result.score_a == 15  # 3 * 5
    assert result.score_b == 15
    assert all(r.move_a == "COOPERATE" and r.move_b == "COOPERATE" for r in result.rounds)


def test_tft_vs_always_defect_settles_into_mutual_defection(backend):
    tft = Automaton(id="tft", source=TIT_FOR_TAT_SOURCE)
    alld = Automaton(id="alld", source=ALWAYS_DEFECT_SOURCE)
    result = match_runner.run_match(tft, alld, backend, length_override=5)
    assert result.status == "completed"
    # round 0: TFT cooperates, AllD defects -> (0, 5); rounds 1-4: mutual defection -> (1,1) each
    assert result.score_a == 0 + 1 * 4
    assert result.score_b == 5 + 1 * 4


def test_tft_vs_grudger_cooperates_forever(backend):
    tft = Automaton(id="tft", source=TIT_FOR_TAT_SOURCE)
    grudger = Automaton(id="grudger", source=GRUDGER_SOURCE)
    result = match_runner.run_match(tft, grudger, backend, length_override=10)
    assert result.status == "completed"
    assert result.score_a == 30
    assert result.score_b == 30


def test_grudger_vs_always_cooperate_cooperates_forever(backend):
    grudger = Automaton(id="grudger", source=GRUDGER_SOURCE)
    allc = Automaton(id="allc", source=ALWAYS_COOPERATE_SOURCE)
    result = match_runner.run_match(grudger, allc, backend, length_override=10)
    assert result.status == "completed"
    assert result.score_a == 30
    assert result.score_b == 30


def test_seeded_match_length_and_result_are_reproducible(backend):
    tft = Automaton(id="tft", source=TIT_FOR_TAT_SOURCE)
    alld = Automaton(id="alld", source=ALWAYS_DEFECT_SOURCE)
    result_a = match_runner.run_match(tft, alld, backend, seed=42)
    result_b = match_runner.run_match(tft, alld, backend, seed=42)
    assert result_a.games_played == result_b.games_played
    assert result_a.score_a == result_b.score_a
    assert result_a.score_b == result_b.score_b
