from __future__ import annotations

import pytest

from tests.conftest import make_player

pytestmark = pytest.mark.integration

# See test_friends_api.py's module docstring-equivalent comment: usernames/ids
# needed after the first request in a test are captured into plain local
# variables right after make_player(), never re-read off the ORM User object
# (a router's db.rollback() on an error path expires the whole session's
# identity map, and touching an expired ORM attribute outside an async
# context raises sqlalchemy's MissingGreenlet).


async def _befriend(a, b, username_a: str, username_b: str) -> None:
    req = (await a.post("/friends/requests", json={"username": username_b})).json()
    await b.post(f"/friends/requests/{req['id']}/accept")


async def _create_automaton(player_client, name: str = "Bot") -> str:
    resp = await player_client.post("/automata", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_get_friend_settings_defaults_to_hide_with_no_row(client, db_session):
    a, _ = await make_player(db_session, username="vis_settings_default")
    resp = await a.get("/friends/settings")
    assert resp.status_code == 200
    assert resp.json() == {"global_mode": "hide", "automaton_ids": []}


async def test_patch_friend_settings_upserts(client, db_session):
    a, _ = await make_player(db_session, username="vis_settings_patch")
    bot_id = await _create_automaton(a, "SettingsBot")

    resp = await a.patch(
        "/friends/settings", json={"global_mode": "specific", "automaton_ids": [bot_id]}
    )
    assert resp.status_code == 200
    assert resp.json() == {"global_mode": "specific", "automaton_ids": [bot_id]}

    # Omitting automaton_ids leaves the allow-list untouched.
    resp2 = await a.patch("/friends/settings", json={"global_mode": "show"})
    assert resp2.json()["global_mode"] == "show"
    assert resp2.json()["automaton_ids"] == [bot_id]


async def test_patch_friend_settings_rejects_unowned_automaton(client, db_session):
    a, _ = await make_player(db_session, username="vis_settings_unowned_a")
    _, user_b = await make_player(db_session, username="vis_settings_unowned_b")
    user_b_id = str(user_b.id)
    resp = await a.patch("/friends/settings", json={"automaton_ids": [user_b_id]})
    assert resp.status_code == 400


async def test_get_visibility_override_requires_friendship(client, db_session):
    a, _ = await make_player(db_session, username="vis_override_notfriend_a")
    _, user_b = await make_player(db_session, username="vis_override_notfriend_b")
    user_b_id = str(user_b.id)
    resp = await a.get(f"/friends/{user_b_id}/visibility-override")
    assert resp.status_code == 404


async def test_get_visibility_override_defaults_when_friends_and_no_row(client, db_session):
    a, user_a = await make_player(db_session, username="vis_override_default_a")
    b, user_b = await make_player(db_session, username="vis_override_default_b")
    username_a, username_b, user_b_id = user_a.username, user_b.username, str(user_b.id)
    await _befriend(a, b, username_a, username_b)

    resp = await a.get(f"/friends/{user_b_id}/visibility-override")
    assert resp.status_code == 200
    assert resp.json() == {"friend_user_id": user_b_id, "mode": "default", "automaton_ids": []}


async def test_patch_visibility_override_upserts_and_rejects_unowned(client, db_session):
    a, user_a = await make_player(db_session, username="vis_override_patch_a")
    b, user_b = await make_player(db_session, username="vis_override_patch_b")
    username_a, username_b, user_b_id = user_a.username, user_b.username, str(user_b.id)
    await _befriend(a, b, username_a, username_b)
    bot_id = await _create_automaton(a, "OverrideBot")

    resp = await a.patch(
        f"/friends/{user_b_id}/visibility-override",
        json={"mode": "specific", "automaton_ids": [bot_id]},
    )
    assert resp.status_code == 200
    assert resp.json()["mode"] == "specific"
    assert resp.json()["automaton_ids"] == [bot_id]

    resp2 = await a.patch(
        f"/friends/{user_b_id}/visibility-override", json={"automaton_ids": [user_b_id]}
    )
    assert resp2.status_code == 400


async def test_profile_requires_friendship(client, db_session):
    a, _ = await make_player(db_session, username="vis_profile_notfriend_a")
    _, user_b = await make_player(db_session, username="vis_profile_notfriend_b")
    user_b_id = str(user_b.id)
    resp = await a.get(f"/friends/{user_b_id}/profile")
    assert resp.status_code == 404


async def test_profile_respects_global_hide_by_default(client, db_session):
    a, user_a = await make_player(db_session, username="vis_profile_hide_a")
    b, user_b = await make_player(db_session, username="vis_profile_hide_b")
    username_a, username_b, user_b_id = user_a.username, user_b.username, str(user_b.id)
    await _befriend(a, b, username_a, username_b)
    await _create_automaton(b, "HiddenBot")

    resp = await a.get(f"/friends/{user_b_id}/profile")
    assert resp.status_code == 200
    assert resp.json()["visible_automata"] == []


async def test_profile_shows_global_show(client, db_session):
    a, user_a = await make_player(db_session, username="vis_profile_show_a")
    b, user_b = await make_player(db_session, username="vis_profile_show_b")
    username_a, username_b, user_b_id = user_a.username, user_b.username, str(user_b.id)
    await _befriend(a, b, username_a, username_b)
    bot_id = await _create_automaton(b, "ShownBot")
    await b.patch("/friends/settings", json={"global_mode": "show"})

    resp = await a.get(f"/friends/{user_b_id}/profile")
    names = [x["name"] for x in resp.json()["visible_automata"]]
    assert names == ["ShownBot"]
    assert resp.json()["visible_automata"][0]["id"] == bot_id


async def test_get_friend_automaton_code_for_a_visible_automaton(client, db_session):
    a, user_a = await make_player(db_session, username="vis_code_a")
    b, user_b = await make_player(db_session, username="vis_code_b")
    username_a, username_b, user_b_id = user_a.username, user_b.username, str(user_b.id)
    await _befriend(a, b, username_a, username_b)
    code = "def decide(history):\n    return DEFECT\n"
    created = await b.post("/automata", json={"name": "CodeBot", "code": code})
    bot_id = created.json()["id"]
    await b.patch("/friends/settings", json={"global_mode": "show"})

    resp = await a.get(f"/friends/{user_b_id}/automata/{bot_id}/code")
    assert resp.status_code == 200
    assert resp.json() == {"code": code}


async def test_get_friend_automaton_code_for_a_hidden_automaton_returns_404(client, db_session):
    a, user_a = await make_player(db_session, username="vis_code_hidden_a")
    b, user_b = await make_player(db_session, username="vis_code_hidden_b")
    username_a, username_b, user_b_id = user_a.username, user_b.username, str(user_b.id)
    await _befriend(a, b, username_a, username_b)
    bot_id = await _create_automaton(b, "HiddenCodeBot")
    # b's global_mode defaults to "hide" - bot_id is not visible to a.

    resp = await a.get(f"/friends/{user_b_id}/automata/{bot_id}/code")
    assert resp.status_code == 404


async def test_get_friend_automaton_code_requires_friendship(client, db_session):
    a, _ = await make_player(db_session, username="vis_code_notfriend_a")
    b, user_b = await make_player(db_session, username="vis_code_notfriend_b")
    user_b_id = str(user_b.id)
    bot_id = await _create_automaton(b, "SomeBot")

    resp = await a.get(f"/friends/{user_b_id}/automata/{bot_id}/code")
    assert resp.status_code == 404


async def test_profile_per_friend_override_wins_over_global(client, db_session):
    a, user_a = await make_player(db_session, username="vis_profile_override_a")
    b, user_b = await make_player(db_session, username="vis_profile_override_b")
    c, user_c = await make_player(db_session, username="vis_profile_override_c")
    username_a, username_b, username_c = user_a.username, user_b.username, user_c.username
    user_a_id, user_b_id = str(user_a.id), str(user_b.id)
    await _befriend(a, b, username_a, username_b)
    await _befriend(c, b, username_c, username_b)
    await _create_automaton(b, "SharedBot")
    await b.patch("/friends/settings", json={"global_mode": "show"})
    # b hides specifically from a, while c (also a friend) still sees it via global "show".
    await b.patch(f"/friends/{user_a_id}/visibility-override", json={"mode": "hide"})

    resp_a = await a.get(f"/friends/{user_b_id}/profile")
    resp_c = await c.get(f"/friends/{user_b_id}/profile")
    assert resp_a.json()["visible_automata"] == []
    assert len(resp_c.json()["visible_automata"]) == 1


async def test_share_with_friends_at_creation_populates_global_and_specific_overrides(
    client, db_session
):
    a, user_a = await make_player(db_session, username="vis_share_a")
    b, user_b = await make_player(db_session, username="vis_share_b")
    c, user_c = await make_player(db_session, username="vis_share_c")
    username_a, username_b, username_c = user_a.username, user_b.username, user_c.username
    user_b_id, user_c_id = str(user_b.id), str(user_c.id)
    await _befriend(a, b, username_a, username_b)
    await _befriend(a, c, username_a, username_c)

    # b is in "specific" mode for a (an existing override); c is still "default".
    await a.patch(
        f"/friends/{user_b_id}/visibility-override", json={"mode": "specific", "automaton_ids": []}
    )

    created = await a.post("/automata", json={"name": "SharedNewBot", "share_with_friends": True})
    assert created.status_code == 201
    new_id = created.json()["id"]

    settings = (await a.get("/friends/settings")).json()
    assert new_id in settings["automaton_ids"]

    override_b = (await a.get(f"/friends/{user_b_id}/visibility-override")).json()
    assert new_id in override_b["automaton_ids"]

    override_c = (await a.get(f"/friends/{user_c_id}/visibility-override")).json()
    assert override_c["mode"] == "default"
    assert new_id not in override_c["automaton_ids"]


async def test_share_with_friends_false_does_not_populate_anything(client, db_session):
    a, _ = await make_player(db_session, username="vis_noshare")
    created = await a.post("/automata", json={"name": "PrivateBot"})
    assert created.status_code == 201

    settings = (await a.get("/friends/settings")).json()
    assert settings == {"global_mode": "hide", "automaton_ids": []}
