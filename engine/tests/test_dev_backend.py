"""Exercises shim/runtime.py end-to-end through a real subprocess (dev_backend),
since there's no way to invoke the shim except by actually spawning it as a
process talking over stdio.
"""

import time

from grudge_engine.protocol import round_message, shutdown_message
from grudge_engine.reference_bots import RANDOM_BOT_SOURCE, TIT_FOR_TAT_SOURCE

BAD_SYNTAX_SOURCE = "def decide(history:\n    return COOPERATE"
MISSING_DECIDE_SOURCE = "x = 1\n"
DISALLOWED_IMPORT_SOURCE = "import os\ndef decide(history):\n    return COOPERATE\n"
RAISES_SOURCE = "def decide(history):\n    raise ValueError('boom')\n"
INVALID_RETURN_SOURCE = "def decide(history):\n    return True\n"
PRINTS_SOURCE = "def decide(history):\n    print('debug from automaton')\n    return COOPERATE\n"
INFINITE_LOOP_SOURCE = "def decide(history):\n    while True:\n        pass\n"


def test_ready_and_one_move_exchange(backend):
    proc = backend.spawn(TIT_FOR_TAT_SOURCE, automaton_id="tft")
    try:
        assert proc.read_line(timeout=5)["type"] == "ready"
        proc.send_line(round_message(0, None))
        msg = proc.read_line(timeout=5)
        assert msg["type"] == "move"
        assert msg["move"] == "COOPERATE"  # TFT cooperates on round 1
        assert msg["round_index"] == 0
        assert msg["cpu_ms"] >= 0.0
        proc.send_line(shutdown_message())
    finally:
        proc.terminate()


def test_missing_decide_is_fatal_error_at_init(backend):
    proc = backend.spawn(MISSING_DECIDE_SOURCE, automaton_id="bad")
    try:
        msg = proc.read_line(timeout=5)
        assert msg["type"] == "fatal_error"
        assert msg["phase"] == "init"
        assert msg["error_type"] == "MissingDecideError"
    finally:
        proc.terminate()


def test_syntax_error_is_fatal_error_at_init(backend):
    proc = backend.spawn(BAD_SYNTAX_SOURCE, automaton_id="bad_syntax")
    try:
        msg = proc.read_line(timeout=5)
        assert msg["type"] == "fatal_error"
        assert msg["phase"] == "init"
    finally:
        proc.terminate()


def test_disallowed_import_is_fatal_error_at_init(backend):
    # The shim re-validates inside the child as defense-in-depth, independent of
    # match_runner's own pre-spawn check (which this test bypasses entirely by
    # talking to the backend directly).
    proc = backend.spawn(DISALLOWED_IMPORT_SOURCE, automaton_id="sneaky")
    try:
        msg = proc.read_line(timeout=5)
        assert msg["type"] == "fatal_error"
        assert msg["phase"] == "init"
    finally:
        proc.terminate()


def test_decide_raising_is_fatal_error_at_round(backend):
    proc = backend.spawn(RAISES_SOURCE, automaton_id="raiser")
    try:
        assert proc.read_line(timeout=5)["type"] == "ready"
        proc.send_line(round_message(0, None))
        msg = proc.read_line(timeout=5)
        assert msg["type"] == "fatal_error"
        assert msg["phase"] == "round"
        assert msg["error_type"] == "ValueError"
        assert msg["round_index"] == 0
    finally:
        proc.terminate()


def test_invalid_return_value_is_fatal_error_at_round(backend):
    proc = backend.spawn(INVALID_RETURN_SOURCE, automaton_id="liar")
    try:
        assert proc.read_line(timeout=5)["type"] == "ready"
        proc.send_line(round_message(0, None))
        msg = proc.read_line(timeout=5)
        assert msg["type"] == "fatal_error"
        assert msg["error_type"] == "InvalidMoveError"
    finally:
        proc.terminate()


def test_print_goes_to_debug_output_not_protocol_stream(backend):
    proc = backend.spawn(PRINTS_SOURCE, automaton_id="chatty")
    try:
        assert proc.read_line(timeout=5)["type"] == "ready"
        proc.send_line(round_message(0, None))
        msg = proc.read_line(timeout=5)
        assert msg["type"] == "move"  # print() didn't corrupt the protocol stream
        proc.send_line(shutdown_message())
        time.sleep(0.2)  # let the stderr reader thread catch up
        assert "debug from automaton" in proc.debug_output()
    finally:
        proc.terminate()


def test_infinite_loop_times_out_without_a_move(backend):
    proc = backend.spawn(INFINITE_LOOP_SOURCE, automaton_id="looper")
    try:
        assert proc.read_line(timeout=5)["type"] == "ready"
        proc.send_line(round_message(0, None))
        msg = proc.read_line(timeout=3)
        assert msg is None  # read_line times out; match_runner is what kills it
    finally:
        proc.terminate()


def _play_n_moves(backend, source, seed, n):
    proc = backend.spawn(source, automaton_id="seeded", seed=seed)
    moves = []
    try:
        assert proc.read_line(timeout=5)["type"] == "ready"
        last_opponent = None
        for i in range(n):
            proc.send_line(round_message(i, last_opponent))
            msg = proc.read_line(timeout=5)
            assert msg["type"] == "move"
            moves.append(msg["move"])
            last_opponent = "COOPERATE"  # arbitrary fixed opponent signal
        proc.send_line(shutdown_message())
    finally:
        proc.terminate()
    return moves


def test_seeded_random_bot_is_reproducible(backend):
    moves_a = _play_n_moves(backend, RANDOM_BOT_SOURCE, seed=12345, n=20)
    moves_b = _play_n_moves(backend, RANDOM_BOT_SOURCE, seed=12345, n=20)
    assert moves_a == moves_b


def test_unseeded_random_bot_runs_without_a_seed_env(backend):
    # Just confirms production (no GRUDGE_SEED) path works at all.
    moves = _play_n_moves(backend, RANDOM_BOT_SOURCE, seed=None, n=5)
    assert len(moves) == 5
