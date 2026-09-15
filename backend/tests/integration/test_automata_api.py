from __future__ import annotations

import pytest
from sqlalchemy import select

from grudge_backend.models.automaton import AutomatonVersion

pytestmark = pytest.mark.integration


async def test_create_automaton_creates_first_version_atomically(auth_client):
    resp = await auth_client.post("/automata", json={"name": "TitForTat"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "TitForTat"
    assert body["active_version_id"] == body["first_version"]["id"]
    assert body["first_version"]["name"] == "v1"


async def test_create_automaton_with_custom_code(auth_client):
    code = "def decide(history):\n    return DEFECT\n"
    resp = await auth_client.post("/automata", json={"name": "AllD", "code": code})
    assert resp.json()["first_version"]["code"] == code


async def test_create_automaton_with_nonexistent_folder_returns_404(auth_client):
    resp = await auth_client.post(
        "/automata", json={"name": "Bot", "folder_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert resp.status_code == 404


async def test_list_and_get_automaton(auth_client):
    created = (await auth_client.post("/automata", json={"name": "Bot"})).json()
    resp = await auth_client.get("/automata")
    assert len(resp.json()) == 1

    resp = await auth_client.get(f"/automata/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


async def test_rename_and_move_automaton(auth_client):
    folder = (await auth_client.post("/folders", json={"name": "Folder"})).json()
    created = (await auth_client.post("/automata", json={"name": "Bot"})).json()

    resp = await auth_client.patch(
        f"/automata/{created['id']}", json={"name": "Renamed", "folder_id": folder["id"]}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"
    assert resp.json()["folder_id"] == folder["id"]


async def test_delete_automaton_cascades_versions(auth_client, db_session):
    created = (await auth_client.post("/automata", json={"name": "Bot"})).json()
    resp = await auth_client.delete(f"/automata/{created['id']}")
    assert resp.status_code == 204

    result = await db_session.execute(
        select(AutomatonVersion).where(AutomatonVersion.automaton_id == created["id"])
    )
    assert result.scalar_one_or_none() is None


async def test_set_active_version(auth_client):
    created = (await auth_client.post("/automata", json={"name": "Bot"})).json()
    new_version = (
        await auth_client.post(f"/automata/{created['id']}/versions", json={"name": "v2"})
    ).json()

    resp = await auth_client.patch(
        f"/automata/{created['id']}/active-version", json={"version_id": new_version["id"]}
    )
    assert resp.status_code == 200
    assert resp.json()["active_version_id"] == new_version["id"]


async def test_set_active_version_rejects_foreign_version(auth_client):
    a = (await auth_client.post("/automata", json={"name": "A"})).json()
    b = (await auth_client.post("/automata", json={"name": "B"})).json()

    resp = await auth_client.patch(
        f"/automata/{a['id']}/active-version", json={"version_id": b["first_version"]["id"]}
    )
    assert resp.status_code == 400


async def test_duplicate_automaton_name_returns_409(auth_client):
    resp1 = await auth_client.post("/automata", json={"name": "Dup"})
    assert resp1.status_code == 201
    resp2 = await auth_client.post("/automata", json={"name": "Dup"})
    assert resp2.status_code == 409


async def test_rename_to_existing_name_returns_409(auth_client):
    await auth_client.post("/automata", json={"name": "Taken"})
    other = (await auth_client.post("/automata", json={"name": "Other"})).json()
    resp = await auth_client.patch(f"/automata/{other['id']}", json={"name": "Taken"})
    assert resp.status_code == 409


async def test_different_users_can_reuse_the_same_name(client, db_session, user, other_user, login):
    await login(client, db_session, user)
    resp = await client.post("/automata", json={"name": "SharedName"})
    assert resp.status_code == 201

    client.cookies.clear()
    await login(client, db_session, other_user)
    resp = await client.post("/automata", json={"name": "SharedName"})
    assert resp.status_code == 201


async def test_cross_user_automaton_access_returns_404(client, db_session, user, other_user, login):
    await login(client, db_session, user)
    created = (await client.post("/automata", json={"name": "Mine"})).json()

    client.cookies.clear()
    await login(client, db_session, other_user)

    resp = await client.get(f"/automata/{created['id']}")
    assert resp.status_code == 404

    resp = await client.delete(f"/automata/{created['id']}")
    assert resp.status_code == 404
