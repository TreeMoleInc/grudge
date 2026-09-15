from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_create_version_forks_active_code_and_does_not_auto_activate(auth_client):
    created = (
        await auth_client.post(
            "/automata",
            json={"name": "Bot", "code": "def decide(history):\n    return COOPERATE\n"},
        )
    ).json()

    resp = await auth_client.post(f"/automata/{created['id']}/versions", json={})
    assert resp.status_code == 201
    new_version = resp.json()
    assert new_version["code"] == created["first_version"]["code"]
    assert new_version["name"] == "v2"

    get_resp = await auth_client.get(f"/automata/{created['id']}")
    assert get_resp.json()["active_version_id"] == created["active_version_id"]


async def test_create_version_with_explicit_code_and_name(auth_client):
    created = (await auth_client.post("/automata", json={"name": "Bot"})).json()
    resp = await auth_client.post(
        f"/automata/{created['id']}/versions",
        json={"name": "Experiment", "code": "def decide(history):\n    return DEFECT\n"},
    )
    body = resp.json()
    assert body["name"] == "Experiment"
    assert body["code"] == "def decide(history):\n    return DEFECT\n"


async def test_patch_version_edits_in_place_no_new_row(auth_client):
    created = (await auth_client.post("/automata", json={"name": "Bot"})).json()
    version_id = created["first_version"]["id"]

    resp = await auth_client.patch(
        f"/automata/{created['id']}/versions/{version_id}",
        json={"code": "def decide(history):\n    return DEFECT\n"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == version_id

    list_resp = await auth_client.get(f"/automata/{created['id']}/versions")
    assert len(list_resp.json()) == 1


async def test_list_versions_summary_excludes_code(auth_client):
    created = (await auth_client.post("/automata", json={"name": "Bot"})).json()
    resp = await auth_client.get(f"/automata/{created['id']}/versions")
    assert "code" not in resp.json()[0]


async def test_get_version_includes_code(auth_client):
    created = (await auth_client.post("/automata", json={"name": "Bot"})).json()
    version_id = created["first_version"]["id"]
    resp = await auth_client.get(f"/automata/{created['id']}/versions/{version_id}")
    assert "code" in resp.json()


async def test_version_for_wrong_automaton_returns_404(auth_client):
    a = (await auth_client.post("/automata", json={"name": "A"})).json()
    b = (await auth_client.post("/automata", json={"name": "B"})).json()

    resp = await auth_client.get(f"/automata/{a['id']}/versions/{b['first_version']['id']}")
    assert resp.status_code == 404


async def test_delete_non_active_version_succeeds(auth_client):
    created = (await auth_client.post("/automata", json={"name": "Bot"})).json()
    v2 = (await auth_client.post(f"/automata/{created['id']}/versions", json={})).json()

    resp = await auth_client.delete(f"/automata/{created['id']}/versions/{v2['id']}")
    assert resp.status_code == 204

    list_resp = await auth_client.get(f"/automata/{created['id']}/versions")
    assert len(list_resp.json()) == 1


async def test_delete_active_version_rejected(auth_client):
    created = (await auth_client.post("/automata", json={"name": "Bot"})).json()
    await auth_client.post(f"/automata/{created['id']}/versions", json={})

    resp = await auth_client.delete(
        f"/automata/{created['id']}/versions/{created['active_version_id']}"
    )
    assert resp.status_code == 409


async def test_delete_only_version_rejected(auth_client):
    created = (await auth_client.post("/automata", json={"name": "Bot"})).json()
    version_id = created["first_version"]["id"]

    resp = await auth_client.delete(f"/automata/{created['id']}/versions/{version_id}")
    assert resp.status_code == 409


async def test_deleting_a_version_does_not_touch_frozen_tournament_snapshots(client, db_session):
    from tests.conftest import make_player

    owner, _ = await make_player(db_session, username="delete_version_owner")
    guest, _ = await make_player(db_session, username="delete_version_guest")

    code = "def decide(history):\n    return COOPERATE\n"
    created = (await owner.post("/automata", json={"name": "Bot", "code": code})).json()
    v2 = (await owner.post(f"/automata/{created['id']}/versions", json={})).json()
    guest_bot = (await guest.post("/automata", json={"name": "GuestBot", "code": code})).json()

    room = (await owner.post("/sim-rooms")).json()
    await owner.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": created["id"]}
    )
    await guest.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": guest_bot["id"]}
    )
    start_resp = await owner.post(f"/sim-rooms/{room['id']}/start")
    tournament_id = start_resp.json()["tournament_id"]

    # Deleting the never-activated v2 must not be blocked by, or affect, the
    # frozen code_snapshot already captured on the tournament's entrants.
    delete_resp = await owner.delete(f"/automata/{created['id']}/versions/{v2['id']}")
    assert delete_resp.status_code == 204

    get_resp = await owner.get(f"/tournaments/{tournament_id}")
    entrant = next(e for e in get_resp.json()["entrants"] if e["automaton_id"] == created["id"])
    assert entrant["code_snapshot"] == code
