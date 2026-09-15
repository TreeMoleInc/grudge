"""Core scoring primitives. Trusted (shim-side) code only — never exposed to player
code, so this module has no restrictions applied to it.
"""

from grudge_engine.constants import PAYOFFS


def payoff(self_move: str, opponent_move: str) -> tuple[int, int]:
    """Return (self_points, opponent_points) for one round."""
    return PAYOFFS[(self_move, opponent_move)]


class Round:
    """One already-played round, as seen from one side. `.me` is this side's own
    move that round, `.opponent` is the other side's move. Deliberately minimal
    (no methods, no dunder overrides beyond what __slots__ requires) so there's
    nothing on this object worth an automaton trying to introspect.
    """

    __slots__ = ("me", "opponent")

    def __init__(self, me: str, opponent: str) -> None:
        self.me = me
        self.opponent = opponent

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"Round(me={self.me!r}, opponent={self.opponent!r})"
