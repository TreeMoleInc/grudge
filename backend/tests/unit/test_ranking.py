from __future__ import annotations

from grudge_backend.services.ranking import rank_with_ties


def test_sequential_ranks_when_no_ties():
    standings = [
        {"automaton_id": "a", "points_per_game": 3},
        {"automaton_id": "b", "points_per_game": 2},
        {"automaton_id": "c", "points_per_game": 1},
    ]
    assert rank_with_ties(standings) == {"a": 1, "b": 2, "c": 3}


def test_equal_points_per_game_share_a_rank_and_skip_the_next():
    standings = [
        {"automaton_id": "a", "points_per_game": 3},
        {"automaton_id": "b", "points_per_game": 3},
        {"automaton_id": "c", "points_per_game": 1},
    ]
    assert rank_with_ties(standings) == {"a": 1, "b": 1, "c": 3}


def test_all_tied():
    standings = [
        {"automaton_id": "a", "points_per_game": 2},
        {"automaton_id": "b", "points_per_game": 2},
        {"automaton_id": "c", "points_per_game": 2},
    ]
    assert rank_with_ties(standings) == {"a": 1, "b": 1, "c": 1}
