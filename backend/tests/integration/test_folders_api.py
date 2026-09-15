from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_create_and_list_folder(auth_client):
    resp = await auth_client.post("/folders", json={"name": "Root"})
    assert resp.status_code == 201
    folder = resp.json()
    assert folder["name"] == "Root"
    assert folder["parent_id"] is None

    resp = await auth_client.get("/folders")
    assert len(resp.json()) == 1


async def test_create_nested_folder(auth_client):
    parent = (await auth_client.post("/folders", json={"name": "Parent"})).json()
    resp = await auth_client.post("/folders", json={"name": "Child", "parent_id": parent["id"]})
    assert resp.status_code == 201
    assert resp.json()["parent_id"] == parent["id"]


async def test_create_folder_with_nonexistent_parent_returns_404(auth_client):
    resp = await auth_client.post(
        "/folders", json={"name": "Orphan", "parent_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert resp.status_code == 404


async def test_rename_folder(auth_client):
    folder = (await auth_client.post("/folders", json={"name": "Old"})).json()
    resp = await auth_client.patch(f"/folders/{folder['id']}", json={"name": "New"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


async def test_move_folder_rejects_self_parent(auth_client):
    folder = (await auth_client.post("/folders", json={"name": "A"})).json()
    resp = await auth_client.patch(f"/folders/{folder['id']}", json={"parent_id": folder["id"]})
    assert resp.status_code == 409


async def test_move_folder_rejects_deeper_cycle(auth_client):
    a = (await auth_client.post("/folders", json={"name": "A"})).json()
    b = (await auth_client.post("/folders", json={"name": "B", "parent_id": a["id"]})).json()
    # Moving A under B would create A -> B -> A.
    resp = await auth_client.patch(f"/folders/{a['id']}", json={"parent_id": b["id"]})
    assert resp.status_code == 409


async def test_move_folder_to_root_via_explicit_null(auth_client):
    a = (await auth_client.post("/folders", json={"name": "A"})).json()
    b = (await auth_client.post("/folders", json={"name": "B", "parent_id": a["id"]})).json()

    resp = await auth_client.patch(f"/folders/{b['id']}", json={"parent_id": None})
    assert resp.status_code == 200
    assert resp.json()["parent_id"] is None


async def test_delete_empty_folder_succeeds(auth_client):
    folder = (await auth_client.post("/folders", json={"name": "Empty"})).json()
    resp = await auth_client.delete(f"/folders/{folder['id']}")
    assert resp.status_code == 204


async def test_delete_nonempty_folder_with_child_folder_rejected(auth_client):
    parent = (await auth_client.post("/folders", json={"name": "Parent"})).json()
    await auth_client.post("/folders", json={"name": "Child", "parent_id": parent["id"]})
    resp = await auth_client.delete(f"/folders/{parent['id']}")
    assert resp.status_code == 409


async def test_delete_nonempty_folder_with_automaton_rejected(auth_client):
    folder = (await auth_client.post("/folders", json={"name": "Home"})).json()
    await auth_client.post("/automata", json={"name": "Bot", "folder_id": folder["id"]})
    resp = await auth_client.delete(f"/folders/{folder['id']}")
    assert resp.status_code == 409


async def test_cross_user_folder_access_returns_404(client, db_session, user, other_user, login):
    await login(client, db_session, user)
    folder = (await client.post("/folders", json={"name": "Mine"})).json()

    client.cookies.clear()
    await login(client, db_session, other_user)

    resp = await client.get("/folders")
    assert resp.json() == []

    resp = await client.patch(f"/folders/{folder['id']}", json={"name": "Hacked"})
    assert resp.status_code == 404

    resp = await client.delete(f"/folders/{folder['id']}")
    assert resp.status_code == 404


async def test_unauthenticated_request_returns_401(client):
    resp = await client.get("/folders")
    assert resp.status_code == 401
