from __future__ import annotations

import pytest

from grudge_backend.services.rating import (
    ELITE_RATING_THRESHOLD,
    K_ELITE,
    K_PROVISIONAL,
    K_STANDARD,
    PROVISIONAL_TOURNAMENTS_THRESHOLD,
    RatingInput,
    compute_rating_updates,
    k_factor,
)


def test_k_factor_provisional_below_threshold():
    assert k_factor(ranked_tournaments_played=0, rating=1000) == K_PROVISIONAL
    assert (
        k_factor(ranked_tournaments_played=PROVISIONAL_TOURNAMENTS_THRESHOLD - 1, rating=1000)
        == K_PROVISIONAL
    )


def test_k_factor_standard_once_past_provisional():
    assert (
        k_factor(ranked_tournaments_played=PROVISIONAL_TOURNAMENTS_THRESHOLD, rating=1000)
        == K_STANDARD
    )
    assert k_factor(ranked_tournaments_played=100, rating=ELITE_RATING_THRESHOLD - 1) == K_STANDARD


def test_k_factor_elite_at_high_rating_past_provisional():
    assert k_factor(ranked_tournaments_played=100, rating=ELITE_RATING_THRESHOLD) == K_ELITE


def test_k_factor_provisional_overrides_elite_rating():
    # A high rating reached quickly (still provisional) stays K_PROVISIONAL -
    # provisional is checked first, per CLAUDE.md S2's stated priority order.
    assert k_factor(ranked_tournaments_played=5, rating=2000) == K_PROVISIONAL


def test_skips_when_every_points_per_game_is_zero():
    entrants = [
        RatingInput(user_id="a", rating=1000, ranked_tournaments_played=0, points_per_game=0),
        RatingInput(user_id="b", rating=1000, ranked_tournaments_played=0, points_per_game=0),
    ]
    assert compute_rating_updates(entrants) is None


def test_skips_when_fewer_than_two_entrants_remain():
    entrants = [
        RatingInput(user_id="a", rating=1000, ranked_tournaments_played=0, points_per_game=3)
    ]
    assert compute_rating_updates(entrants) is None


def test_symmetric_ratings_and_scores_yield_zero_delta():
    entrants = [
        RatingInput(user_id="a", rating=1000, ranked_tournaments_played=0, points_per_game=2),
        RatingInput(user_id="b", rating=1000, ranked_tournaments_played=0, points_per_game=2),
    ]
    updates = compute_rating_updates(entrants)
    assert updates is not None
    for update in updates:
        assert update.delta == pytest.approx(0.0, abs=1e-9)
        assert update.new_rating == update.rating_before


def test_outperforming_expectation_yields_positive_delta():
    # Equal starting ratings (E_i = 0.5 for both) but "a" scores much better
    # than "b" (S_a > 0.5) - "a" should gain rating, "b" should lose it.
    entrants = [
        RatingInput(user_id="a", rating=1000, ranked_tournaments_played=0, points_per_game=4),
        RatingInput(user_id="b", rating=1000, ranked_tournaments_played=0, points_per_game=1),
    ]
    updates = {u.user_id: u for u in compute_rating_updates(entrants)}
    assert updates["a"].delta > 0
    assert updates["b"].delta < 0


def test_e_and_s_sum_to_one_across_the_tournament():
    entrants = [
        RatingInput(user_id="a", rating=1200, ranked_tournaments_played=10, points_per_game=3.5),
        RatingInput(user_id="b", rating=900, ranked_tournaments_played=40, points_per_game=2.0),
        RatingInput(user_id="c", rating=1600, ranked_tournaments_played=5, points_per_game=1.0),
        RatingInput(user_id="d", rating=1000, ranked_tournaments_played=100, points_per_game=0.5),
    ]
    updates = compute_rating_updates(entrants)
    assert updates is not None
    assert sum(u.e_i for u in updates) == pytest.approx(1.0, abs=1e-9)
    assert sum(u.s_i for u in updates) == pytest.approx(1.0, abs=1e-9)


def test_deltas_sum_to_zero_even_with_differing_k_factors():
    # Deliberately mixes a provisional player (K=32) with an elite one
    # (K=10) so the zero-sum correction is actually exercised, not
    # trivially zero because every K happens to match.
    entrants = [
        RatingInput(user_id="new", rating=1000, ranked_tournaments_played=0, points_per_game=3.2),
        RatingInput(
            user_id="elite", rating=1900, ranked_tournaments_played=200, points_per_game=1.8
        ),
        RatingInput(user_id="mid", rating=1300, ranked_tournaments_played=50, points_per_game=1.0),
    ]
    updates = compute_rating_updates(entrants)
    assert updates is not None
    assert sum(u.delta for u in updates) == pytest.approx(0.0, abs=1e-9)
