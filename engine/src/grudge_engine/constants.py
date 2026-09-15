"""Game constants and tunables. See CLAUDE.md sections 1-3 for the full rationale
behind every value here — this module just holds the numbers, not the reasoning.
"""

# Ambient move constants injected into an automaton's namespace. These are plain
# strings under the hood (no enum/class machinery needed) but player code should
# always use the names, never the literal strings.
COOPERATE = "COOPERATE"
DEFECT = "DEFECT"
C = COOPERATE
D = DEFECT

VALID_MOVES = frozenset({COOPERATE, DEFECT})

# Payoff matrix (points awarded to (self, opponent) for a given (self_move, opponent_move)).
PAYOFFS = {
    (COOPERATE, COOPERATE): (3, 3),
    (COOPERATE, DEFECT): (0, 5),
    (DEFECT, COOPERATE): (5, 0),
    (DEFECT, DEFECT): (1, 1),
}

# Match length: geometric distribution over per-round continuation probability,
# clamped to a hard [MIN_LENGTH, MAX_LENGTH] range.
CONTINUATION_PROBABILITY = 0.99667  # w; expected length ~= 1 / (1 - w) ~= 300
MIN_LENGTH = 50
MAX_LENGTH = 1500

# Time/memory limits (see CLAUDE.md "Time/memory limit values: confirmed").
PER_ROUND_CPU_MS = 250
PER_MATCH_CUMULATIVE_CPU_MS = 10_000
WALL_CLOCK_BACKSTOP_S = 2.0
MEMORY_LIMIT_MB = 128

# Preflight check: number of rounds played against the fixed Random reference bot.
PREFLIGHT_NUM_GAMES = 10

# Exclusive upper bound for a derived per-side/per-match RNG seed
# (rng.randrange(SEED_UPPER_BOUND) in match_runner.py/tournament_runner.py).
# Centralized so the three call sites can't drift out of sync with each other.
SEED_UPPER_BOUND = 2**31

# No TOURNAMENT_SIZE constant here on purpose: run_tournament() is N-generic
# (itertools.combinations over whatever entrant list it's given, see
# tournament_runner.py) - the fixed ranked/unranked room size is a product-layer
# decision, not an engine one, and lives in backend/services/matchmaking.py's
# RANKED_ROOM_SIZE/UNRANKED_ROOM_SIZE instead.
