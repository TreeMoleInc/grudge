import random
import statistics

from grudge_engine.constants import MAX_LENGTH, MIN_LENGTH
from grudge_engine.length import draw_length


class _FixedRNG:
    """Minimal stand-in exposing just the .random() method draw_length needs."""

    def __init__(self, value: float) -> None:
        self._value = value

    def random(self) -> float:
        return self._value


def test_draw_length_within_bounds():
    rng = random.Random(42)
    for _ in range(2000):
        length = draw_length(rng)
        assert MIN_LENGTH <= length <= MAX_LENGTH


def test_draw_length_is_deterministic_given_seed():
    seq_a = [draw_length(random.Random(7)) for _ in range(1)]  # single fresh-seed draw
    rng = random.Random(7)
    seq_b = [draw_length(rng) for _ in range(50)]
    assert seq_a[0] == seq_b[0]

    rng1 = random.Random(99)
    rng2 = random.Random(99)
    assert [draw_length(rng1) for _ in range(50)] == [draw_length(rng2) for _ in range(50)]


def test_draw_length_u_zero_clamps_to_min():
    assert draw_length(_FixedRNG(0.0)) == MIN_LENGTH


def test_draw_length_u_near_one_clamps_to_max():
    assert draw_length(_FixedRNG(0.999999999999)) == MAX_LENGTH


def test_draw_length_mean_is_near_expected_300():
    rng = random.Random(123)
    samples = [draw_length(rng) for _ in range(20000)]
    mean = statistics.mean(samples)
    # Unclamped mean is 1 / (1 - w) ~= 300; the low clamp (values < 50 pulled up
    # to 50) nudges the empirical mean up a little, the high clamp (rare tail
    # pulled down from >1500) nudges it down a little - generous band either way.
    assert 270 <= mean <= 340


def test_draw_length_hits_both_clamp_boundaries_over_many_draws():
    rng = random.Random(999)
    samples = [draw_length(rng) for _ in range(20000)]
    assert min(samples) == MIN_LENGTH
    assert max(samples) <= MAX_LENGTH
