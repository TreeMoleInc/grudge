import pytest

from grudge_engine.automaton import Automaton
from grudge_engine.reference_bots import (
    ALWAYS_COOPERATE_SOURCE,
    ALWAYS_DEFECT_SOURCE,
    GRUDGER_SOURCE,
    RANDOM_BOT_SOURCE,
    TIT_FOR_TAT_SOURCE,
)
from grudge_engine.results import MatchResult
from grudge_engine.tournament_runner import _reason_for, run_tournament

BROKEN_SOURCE = "def decide(history):\n    raise ValueError('boom')\n"


def _voided_match(**overrides) -> MatchResult:
    fields = {
        "automaton_a_id": "a",
        "automaton_b_id": "b",
        "games_played": 0,
        "score_a": 0,
        "score_b": 0,
        "rounds": (),
        "status": "voided",
        "voided_side": "both",
        "void_reason": "A's own reason. B's own reason.",
        "void_reason_a": "A's own reason.",
        "void_reason_b": "B's own reason.",
        "debug_log_a": "",
        "debug_log_b": "",
    }
    fields.update(overrides)
    return MatchResult(**fields)


def test_reason_for_never_blends_the_other_sides_fault_text():
    match = _voided_match()
    assert _reason_for(match, "a") == "A's own reason."
    assert _reason_for(match, "b") == "B's own reason."
    assert "B's own reason" not in _reason_for(match, "a")
    assert "A's own reason" not in _reason_for(match, "b")


def test_reason_for_falls_back_to_combined_reason_if_a_per_side_reason_is_missing():
    # Defensive fallback only - every real _void_result call site always sets
    # the per-side field for a side that's actually in voided_side (see
    # match_runner.py), but this keeps the lookup itself safe if that
    # invariant is ever violated rather than surfacing None/a KeyError.
    match = _voided_match(void_reason_a=None)
    assert _reason_for(match, "a") == "A's own reason. B's own reason."


def test_faulted_automaton_voids_all_its_matches_but_others_stay_intact(backend):
    automata = [
        Automaton(id="allc", source=ALWAYS_COOPERATE_SOURCE),
        Automaton(id="broken", source=BROKEN_SOURCE),
        Automaton(id="tft", source=TIT_FOR_TAT_SOURCE),
    ]
    result = run_tournament(automata, backend, seed=1)

    assert len(result.matches) == 3  # 3 choose 2
    faulted_ids = {f.automaton_id for f in result.faulted}
    assert faulted_ids == {"broken"}

    standing_ids = {s.automaton_id for s in result.standings}
    assert standing_ids == {"allc", "tft"}  # broken excluded entirely

    # the allc-vs-tft match never involved "broken" and completed cleanly, so it
    # still counts, even though the tournament as a whole had a fault in it
    for standing in result.standings:
        assert standing.points_per_game == pytest.approx(3.0)  # mutual cooperation
        assert standing.total_games >= 50  # unseeded-length match, min clamp

    broken_entry = next(f for f in result.faulted if f.automaton_id == "broken")
    assert len(broken_entry.voided_match_ids) == 2  # both matches broken played in


def test_on_match_complete_fires_once_per_match_with_running_totals(backend):
    automata = [
        Automaton(id="allc", source=ALWAYS_COOPERATE_SOURCE),
        Automaton(id="alld", source=ALWAYS_DEFECT_SOURCE),
        Automaton(id="tft", source=TIT_FOR_TAT_SOURCE),
    ]
    progress: list[tuple[int, int]] = []

    def on_match_complete(match, completed, total):
        assert match.status in ("completed", "voided")
        progress.append((completed, total))

    run_tournament(
        automata, backend, seed=1, length_override=5, on_match_complete=on_match_complete
    )

    assert progress == [(1, 3), (2, 3), (3, 3)]  # 3 choose 2, in order, no gaps/repeats


def test_on_match_complete_defaults_to_none_and_changes_nothing(backend):
    automata = [
        Automaton(id="allc", source=ALWAYS_COOPERATE_SOURCE),
        Automaton(id="tft", source=TIT_FOR_TAT_SOURCE),
    ]
    # No on_match_complete passed - must behave exactly as before its addition.
    result = run_tournament(automata, backend, seed=1, length_override=5)
    assert len(result.matches) == 1


def test_classic_axelrod_pattern_holds_in_a_seeded_round_robin(backend):
    automata = [
        Automaton(id="tft", source=TIT_FOR_TAT_SOURCE),
        Automaton(id="allc", source=ALWAYS_COOPERATE_SOURCE),
        Automaton(id="alld", source=ALWAYS_DEFECT_SOURCE),
        Automaton(id="grudger", source=GRUDGER_SOURCE),
        Automaton(id="random", source=RANDOM_BOT_SOURCE),
    ]
    # Every match gets the same fixed length here (rather than each drawing its
    # own random length) specifically so the game-count-weighted aggregate
    # points-per-game reflects real strategy strength, not which pairing
    # happened to draw a longer/shorter match by chance.
    result = run_tournament(automata, backend, seed=2024, length_override=100)

    assert len(result.matches) == 10  # 5 choose 2
    assert result.faulted == ()

    by_id = {s.automaton_id: s.points_per_game for s in result.standings}
    assert set(by_id) == {"tft", "allc", "alld", "grudger", "random"}

    # The classic Axelrod finding: a purely exploitative strategy doesn't win
    # outright once reciprocal "nice" strategies are in the field.
    ranked = sorted(by_id, key=lambda k: by_id[k], reverse=True)
    assert ranked[0] != "alld"

    # AllC is the most exploitable strategy present (everyone can defect on it
    # for free, forever, with no retaliation) - it should not out-score the
    # reciprocal strategies, which only ever get exploited for one round before
    # retaliating.
    assert by_id["allc"] <= by_id["tft"]
    assert by_id["allc"] <= by_id["grudger"]


def test_tournament_is_not_restricted_to_exactly_four_automata(backend):
    # Sims/custom tournaments explicitly don't require exactly 4 per CLAUDE.md -
    # only the standard ranked/unranked "Play" flow does, and that's a
    # product/queue-level constraint, not an engine one.
    automata = [
        Automaton(id="allc", source=ALWAYS_COOPERATE_SOURCE),
        Automaton(id="tft", source=TIT_FOR_TAT_SOURCE),
    ]
    result = run_tournament(automata, backend, seed=1)
    assert len(result.matches) == 1
