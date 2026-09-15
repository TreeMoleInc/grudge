"""Randomized match length: geometric distribution over a per-round continuation
probability, clamped to a hard [MIN_LENGTH, MAX_LENGTH] range. See CLAUDE.md
section 1 "Game rules (confirmed)" for the full rationale.
"""

import math
import random

from grudge_engine.constants import CONTINUATION_PROBABILITY, MAX_LENGTH, MIN_LENGTH


def draw_length(rng: random.Random) -> int:
    """Draw a match length (number of rounds) from Geometric(1 - w), via inverse
    transform sampling, then clamp to [MIN_LENGTH, MAX_LENGTH].

    Memorylessness of the geometric distribution is what actually prevents
    end-game defection: the per-round continuation probability never changes
    regardless of how many rounds have already been played, so a bot can never
    infer "we must be near the end" from the round count alone.
    """
    u = rng.random()  # U ~ Uniform[0, 1)
    raw = math.ceil(math.log(1.0 - u) / math.log(CONTINUATION_PROBABILITY))
    return min(max(raw, MIN_LENGTH), MAX_LENGTH)
