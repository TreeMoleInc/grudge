from grudge_engine.protocol import (
    FAULT_TYPES,
    decode_line,
    encode_line,
    fatal_error_message,
    move_message,
    protocol_error_message,
    ready_message,
    round_message,
    shutdown_message,
)


def test_round_message_first_round_has_null_opponent_move():
    msg = round_message(0, None)
    assert msg["round_index"] == 0
    assert msg["opponent_last_move"] is None


def test_round_message_carries_opponent_last_move():
    msg = round_message(5, "DEFECT")
    assert msg["round_index"] == 5
    assert msg["opponent_last_move"] == "DEFECT"


def test_encode_decode_round_trip():
    msg = move_message(5, "COOPERATE", 1.23)
    assert decode_line(encode_line(msg)) == msg


def test_fault_types_cover_fatal_and_protocol_errors_only():
    assert fatal_error_message("init", "X", "y")["type"] in FAULT_TYPES
    assert protocol_error_message("bad")["type"] in FAULT_TYPES
    assert ready_message()["type"] not in FAULT_TYPES
    assert shutdown_message()["type"] not in FAULT_TYPES
    assert move_message(0, "COOPERATE", 0.0)["type"] not in FAULT_TYPES


def test_fatal_error_round_index_omitted_when_not_given():
    msg = fatal_error_message("init", "X", "y")
    assert "round_index" not in msg


def test_fatal_error_round_index_included_when_given():
    msg = fatal_error_message("round", "X", "y", round_index=3)
    assert msg["round_index"] == 3
