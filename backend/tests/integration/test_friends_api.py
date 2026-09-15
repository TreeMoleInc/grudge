from __future__ import annotations

import pytest

from tests.conftest import make_player

pytestmark = pytest.mark.integration

# Every username/id used after the first request in a test is captured into a
# plain local variable right after make_player() and never re-read off the
# ORM User object again - a router's db.rollback() on an error path (e.g. the
# 409 handlers below) expires every object in the shared db_session's
# identity map, and a later plain (non-awaited) attribute access on an
# expired ORM object raises sqlalchemy's MissingGreenlet, since the lazy
# reload it'd trigger has no async context to run in from plain test code.


async def test_send_request_success(client, db_session):
    a, _ = await make_player(db_session, username="req_a")
    _, user_b = await make_player(db_session, username="req_b")
    user_b_id = str(user_b.id)

    resp = await a.post("/friends/requests", json={"username": "req_b"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["from_username"] == "req_a"
    assert body["to_username"] == "req_b"
    assert body["to_user_id"] == user_b_id


async def test_send_request_unknown_username_returns_404(client, db_session):
    a, _ = await make_player(db_session, username="req_unknown")
    resp = await a.post("/friends/requests", json={"username": "does_not_exist"})
    assert resp.status_code == 404


async def test_send_request_to_self_returns_400(client, db_session):
    a, user_a = await make_player(db_session, username="req_self")
    resp = await a.post("/friends/requests", json={"username": user_a.username})
    assert resp.status_code == 400


async def test_duplicate_pending_request_returns_409_both_directions(client, db_session):
    a, user_a = await make_player(db_session, username="req_dup_a")
    b, user_b = await make_player(db_session, username="req_dup_b")
    username_a, username_b = user_a.username, user_b.username

    resp1 = await a.post("/friends/requests", json={"username": username_b})
    assert resp1.status_code == 201

    # Same direction again.
    resp2 = await a.post("/friends/requests", json={"username": username_b})
    assert resp2.status_code == 409

    # Reverse direction while the first is still pending.
    resp3 = await b.post("/friends/requests", json={"username": username_a})
    assert resp3.status_code == 409


async def test_already_friends_returns_409(client, db_session):
    a, _ = await make_player(db_session, username="req_already_a")
    b, user_b = await make_player(db_session, username="req_already_b")
    username_b = user_b.username

    req = (await a.post("/friends/requests", json={"username": username_b})).json()
    accept_resp = await b.post(f"/friends/requests/{req['id']}/accept")
    assert accept_resp.status_code == 200

    resp = await a.post("/friends/requests", json={"username": username_b})
    assert resp.status_code == 409


async def test_list_incoming_and_outgoing_requests(client, db_session):
    a, user_a = await make_player(db_session, username="req_list_a")
    b, user_b = await make_player(db_session, username="req_list_b")
    username_a, username_b = user_a.username, user_b.username

    await a.post("/friends/requests", json={"username": username_b})

    incoming_b = (await b.get("/friends/requests/incoming")).json()
    assert len(incoming_b) == 1
    assert incoming_b[0]["from_username"] == username_a

    outgoing_a = (await a.get("/friends/requests/outgoing")).json()
    assert len(outgoing_a) == 1
    assert outgoing_a[0]["to_username"] == username_b

    assert (await a.get("/friends/requests/incoming")).json() == []
    assert (await b.get("/friends/requests/outgoing")).json() == []


async def test_accept_request_creates_symmetric_friendship_and_deletes_request(client, db_session):
    a, user_a = await make_player(db_session, username="req_accept_a")
    b, user_b = await make_player(db_session, username="req_accept_b")
    username_a, username_b = user_a.username, user_b.username

    req = (await a.post("/friends/requests", json={"username": username_b})).json()
    resp = await b.post(f"/friends/requests/{req['id']}/accept")
    assert resp.status_code == 200
    assert resp.json()["username"] == username_a

    friends_a = (await a.get("/friends")).json()
    friends_b = (await b.get("/friends")).json()
    assert [f["username"] for f in friends_a] == [username_b]
    assert [f["username"] for f in friends_b] == [username_a]

    # Request row is gone - re-sending should work again (no leftover row blocking it).
    assert (await a.get("/friends/requests/outgoing")).json() == []


async def test_accept_request_not_addressed_to_you_returns_404(client, db_session):
    a, _ = await make_player(db_session, username="req_wrong_a")
    _, user_b = await make_player(db_session, username="req_wrong_b")
    username_b = user_b.username

    req = (await a.post("/friends/requests", json={"username": username_b})).json()
    # The sender tries to accept their own outgoing request.
    resp = await a.post(f"/friends/requests/{req['id']}/accept")
    assert resp.status_code == 404


async def test_decline_by_recipient_and_cancel_by_sender(client, db_session):
    a, _ = await make_player(db_session, username="req_decline_a")
    b, user_b = await make_player(db_session, username="req_decline_b")
    username_b = user_b.username

    req = (await a.post("/friends/requests", json={"username": username_b})).json()
    resp = await b.delete(f"/friends/requests/{req['id']}")
    assert resp.status_code == 204
    assert (await a.get("/friends/requests/outgoing")).json() == []

    # A fresh request can be cancelled by its own sender.
    req2 = (await a.post("/friends/requests", json={"username": username_b})).json()
    resp2 = await a.delete(f"/friends/requests/{req2['id']}")
    assert resp2.status_code == 204
    assert (await b.get("/friends/requests/incoming")).json() == []


async def test_remove_request_by_third_party_returns_404(client, db_session):
    a, _ = await make_player(db_session, username="req_third_a")
    _, user_b = await make_player(db_session, username="req_third_b")
    c, _ = await make_player(db_session, username="req_third_c")
    username_b = user_b.username

    req = (await a.post("/friends/requests", json={"username": username_b})).json()
    resp = await c.delete(f"/friends/requests/{req['id']}")
    assert resp.status_code == 404


async def test_unfriend_removes_both_directions_and_clears_overrides(client, db_session):
    a, _ = await make_player(db_session, username="unfriend_a")
    b, user_b = await make_player(db_session, username="unfriend_b")
    username_b, user_b_id = user_b.username, str(user_b.id)

    req = (await a.post("/friends/requests", json={"username": username_b})).json()
    await b.post(f"/friends/requests/{req['id']}/accept")

    override_resp = await a.patch(
        f"/friends/{user_b_id}/visibility-override", json={"mode": "hide"}
    )
    assert override_resp.status_code == 200

    resp = await a.delete(f"/friends/{user_b_id}")
    assert resp.status_code == 204

    assert (await a.get("/friends")).json() == []
    assert (await b.get("/friends")).json() == []

    # Re-friending starts clean - no stale "hide" override survives.
    req2 = (await a.post("/friends/requests", json={"username": username_b})).json()
    await b.post(f"/friends/requests/{req2['id']}/accept")
    override_after = (await a.get(f"/friends/{user_b_id}/visibility-override")).json()
    assert override_after["mode"] == "default"


async def test_unfriend_when_not_friends_returns_404(client, db_session):
    a, _ = await make_player(db_session, username="unfriend_none_a")
    _, user_b = await make_player(db_session, username="unfriend_none_b")
    user_b_id = str(user_b.id)
    resp = await a.delete(f"/friends/{user_b_id}")
    assert resp.status_code == 404
