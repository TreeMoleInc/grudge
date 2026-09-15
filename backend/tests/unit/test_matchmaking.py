from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from grudge_backend.services.matchmaking import (
    group_is_compatible,
    is_stale,
    room_accepts,
    window_radius,
)


@pytest.mark.parametrize(
    "elapsed_seconds,expected",
    [
        (0, 100),
        (14.9, 100),
        (15, 150),
        (29.9, 150),
        (30, 200),
        (44, 200),
        (45, 250),
        (119.9, 450),  # 119.9 // 15 == 7 -> 100 + 50*7
        (120, None),
        (500, None),
    ],
)
def test_window_radius(elapsed_seconds, expected):
    assert window_radius(elapsed_seconds) == expected


def test_group_is_compatible_within_tightest_radius():
    # Two players 100 apart, tightest active radius is 100 -> exactly fits.
    assert group_is_compatible([100, 100], spread=100) is True


def test_group_is_compatible_exceeds_tightest_radius():
    # 101 apart with a 100 radius -> just over the line.
    assert group_is_compatible([100, 100], spread=101) is False


def test_group_is_compatible_uses_the_most_restrictive_member():
    # One player has widened to 650, but another is still at the initial 100 -
    # the group must fit inside the tighter one.
    assert group_is_compatible([650, 100], spread=150) is False
    assert group_is_compatible([650, 100], spread=100) is True


def test_group_is_compatible_true_when_all_constraints_dropped():
    assert group_is_compatible([None, None], spread=10_000) is True


def test_group_is_compatible_true_when_some_dropped_but_active_ones_still_fit():
    assert group_is_compatible([None, 200], spread=150) is True
    assert group_is_compatible([None, 200], spread=250) is False


def test_room_accepts_is_group_is_compatible_plus_candidate():
    assert room_accepts(existing_radii=[100], candidate_radius=100, spread=100) is True
    assert room_accepts(existing_radii=[100], candidate_radius=100, spread=150) is False


def test_is_stale():
    now = datetime.now(UTC)
    assert is_stale(now - timedelta(seconds=29), now) is False
    assert is_stale(now - timedelta(seconds=31), now) is True
    assert is_stale(now - timedelta(seconds=100), now, threshold_seconds=200) is False
