from __future__ import annotations

import uuid

import pytest

from grudge_backend.services.visibility import resolve_visible_automaton_ids

A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
ALL = {A, B, C}


def resolve(
    global_mode,
    global_allow_ids=frozenset(),
    override_mode="default",
    override_allow_ids=frozenset(),
):
    return resolve_visible_automaton_ids(
        global_mode=global_mode,
        global_allow_ids=set(global_allow_ids),
        override_mode=override_mode,
        override_allow_ids=set(override_allow_ids),
        all_owner_automaton_ids=set(ALL),
    )


def test_global_show_with_no_override_reveals_everything():
    assert resolve("show") == ALL


def test_global_hide_with_no_override_reveals_nothing():
    assert resolve("hide") == set()


def test_global_specific_with_no_override_reveals_only_the_allowlist():
    assert resolve("specific", global_allow_ids={A, B}) == {A, B}


def test_override_hide_narrows_an_otherwise_show_global_setting():
    assert resolve("show", override_mode="hide") == set()


def test_override_show_widens_an_otherwise_hide_global_setting():
    assert resolve("hide", override_mode="show") == ALL


def test_override_specific_uses_its_own_allowlist_not_the_global_one():
    result = resolve(
        "specific", global_allow_ids={A}, override_mode="specific", override_allow_ids={B, C}
    )
    assert result == {B, C}


def test_override_default_falls_through_to_global():
    assert resolve("specific", global_allow_ids={A, C}, override_mode="default") == {A, C}


def test_specific_allowlist_id_no_longer_owned_is_excluded_defensively():
    stale_id = uuid.uuid4()
    assert resolve("specific", global_allow_ids={A, stale_id}) == {A}


def test_empty_owner_automata_returns_empty_regardless_of_mode():
    for mode in ("show", "hide", "specific"):
        result = resolve_visible_automaton_ids(
            global_mode=mode,
            global_allow_ids={A},
            override_mode="default",
            override_allow_ids=set(),
            all_owner_automaton_ids=set(),
        )
        assert result == set()


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        resolve("bogus")  # type: ignore[arg-type]
