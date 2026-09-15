import pytest

from grudge_engine.constants import COOPERATE, DEFECT
from grudge_engine.game import Round, payoff


@pytest.mark.parametrize(
    "self_move,opponent_move,expected",
    [
        (COOPERATE, COOPERATE, (3, 3)),
        (DEFECT, DEFECT, (1, 1)),
        (DEFECT, COOPERATE, (5, 0)),
        (COOPERATE, DEFECT, (0, 5)),
    ],
)
def test_payoff_matrix(self_move, opponent_move, expected):
    assert payoff(self_move, opponent_move) == expected


def test_round_record_attribute_access():
    r = Round(me=COOPERATE, opponent=DEFECT)
    assert r.me == COOPERATE
    assert r.opponent == DEFECT
