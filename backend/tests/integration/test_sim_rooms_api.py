from __future__ import annotations

import pytest
from sqlalchemy import select

from grudge_backend.models.tournament import Tournament
from tests.conftest import make_player

pytestmark = pytest.mark.integration

_COOPERATE_CODE = "def decide(history):\n    return COOPERATE\n"


async def _create_automaton(player_client, name: str = "Bot") -> str:
    resp = await player_client.post("/automata", json={"name": name, "code": _COOPERATE_CODE})
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_create_join_start_flow(client, db_session):
    owner, _ = await make_player(db_session, username="sim_owner")
    guest, _ = await make_player(db_session, username="sim_guest")

    create_resp = await owner.post("/sim-rooms")
    assert create_resp.status_code == 201
    room = create_resp.json()
    assert len(room["invite_code"]) == 8

    owner_bot = await _create_automaton(owner, "OwnerBot")
    guest_bot = await _create_automaton(guest, "GuestBot")

    join_owner = await owner.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": owner_bot}
    )
    assert join_owner.status_code == 201
    join_guest = await guest.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": guest_bot}
    )
    assert join_guest.status_code == 201

    start_resp = await owner.post(f"/sim-rooms/{room['id']}/start")
    assert start_resp.status_code == 200
    tournament_id = start_resp.json()["tournament_id"]

    result = await db_session.execute(select(Tournament).where(Tournament.id == tournament_id))
    tournament = result.scalar_one()
    assert tournament.type == "sim"
    assert len(tournament.entrants) == 2
    # Phase 4: entrants now carry a name snapshot, immutable even if the
    # automaton/owner is later renamed - needed so Results pages can show
    # opponent names instead of raw UUIDs.
    names = {e["automaton_name"] for e in tournament.entrants}
    assert names == {"OwnerBot", "GuestBot"}
    usernames = {e["owner_username"] for e in tournament.entrants}
    assert usernames == {"sim_owner", "sim_guest"}
    version_names = {e["automaton_version_name"] for e in tournament.entrants}
    assert version_names == {"v1"}  # both automata just-created, first version

    get_resp = await owner.get(f"/tournaments/{tournament_id}")
    assert get_resp.status_code == 200
    entrants = get_resp.json()["entrants"]
    assert {e["automaton_name"] for e in entrants} == {"OwnerBot", "GuestBot"}


async def test_get_room_returns_state_for_hydration(client, db_session):
    owner, _ = await make_player(db_session, username="sim_get_owner")
    guest, _ = await make_player(db_session, username="sim_get_guest")

    room = (await owner.post("/sim-rooms")).json()
    owner_bot = await _create_automaton(owner, "OwnerBot")
    await owner.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": owner_bot}
    )

    # Any authenticated user can fetch room state (invite-code rooms are
    # shared/not-secret, same reasoning as GET /tournaments/{id}) - not just
    # the owner or an existing member.
    resp = await guest.get(f"/sim-rooms/{room['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["invite_code"] == room["invite_code"]
    assert body["status"] == "open"
    assert len(body["entries"]) == 1
    assert body["entries"][0]["automaton_id"] == owner_bot


async def test_join_response_and_room_state_include_automaton_and_owner_names(client, db_session):
    owner, _ = await make_player(db_session, username="sim_names_owner")
    room = (await owner.post("/sim-rooms")).json()
    owner_bot = await _create_automaton(owner, "NamedBot")

    join_resp = await owner.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": owner_bot}
    )
    assert join_resp.status_code == 201
    assert join_resp.json()["automaton_name"] == "NamedBot"
    assert join_resp.json()["owner_username"] == "sim_names_owner"

    get_resp = await owner.get(f"/sim-rooms/{room['id']}")
    entry = get_resp.json()["entries"][0]
    assert entry["automaton_name"] == "NamedBot"
    assert entry["owner_username"] == "sim_names_owner"


async def test_get_nonexistent_room_returns_404(client, db_session):
    player, _ = await make_player(db_session, username="sim_get_missing")
    resp = await player.get("/sim-rooms/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_join_with_wrong_code_returns_404(client, db_session):
    player, _ = await make_player(db_session, username="sim_wrong_code")
    bot = await _create_automaton(player)
    resp = await player.post("/sim-rooms/join", json={"code": "NOSUCH01", "automaton_id": bot})
    assert resp.status_code == 404


async def test_non_owner_cannot_start_room(client, db_session):
    owner, _ = await make_player(db_session, username="sim_not_owner_a")
    other, _ = await make_player(db_session, username="sim_not_owner_b")

    room = (await owner.post("/sim-rooms")).json()
    owner_bot = await _create_automaton(owner, "A")
    other_bot = await _create_automaton(other, "B")
    await owner.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": owner_bot}
    )
    await other.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": other_bot}
    )

    resp = await other.post(f"/sim-rooms/{room['id']}/start")
    assert resp.status_code == 403


async def test_starting_with_too_few_entrants_returns_400(client, db_session):
    owner, _ = await make_player(db_session, username="sim_too_few")
    room = (await owner.post("/sim-rooms")).json()
    bot = await _create_automaton(owner)
    await owner.post("/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": bot})

    resp = await owner.post(f"/sim-rooms/{room['id']}/start")
    assert resp.status_code == 400


async def test_duplicate_automaton_entry_returns_409(client, db_session):
    owner, _ = await make_player(db_session, username="sim_duplicate")
    room = (await owner.post("/sim-rooms")).json()
    bot = await _create_automaton(owner)

    resp1 = await owner.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": bot}
    )
    assert resp1.status_code == 201
    resp2 = await owner.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": bot}
    )
    assert resp2.status_code == 409


async def test_remove_entry_by_owner(client, db_session):
    owner, _ = await make_player(db_session, username="sim_remove_owner")
    guest, _ = await make_player(db_session, username="sim_remove_guest")

    room = (await owner.post("/sim-rooms")).json()
    guest_bot = await _create_automaton(guest, "GuestBot")
    entry = (
        await guest.post(
            "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": guest_bot}
        )
    ).json()

    resp = await owner.delete(f"/sim-rooms/{room['id']}/entries/{entry['id']}")
    assert resp.status_code == 204


async def _befriend(a, b, username_a: str, username_b: str) -> None:
    req = (await a.post("/friends/requests", json={"username": username_b})).json()
    await b.post(f"/friends/requests/{req['id']}/accept")


async def test_invite_friend_to_room_appears_in_their_invite_list(client, db_session):
    owner, user_owner = await make_player(db_session, username="sim_invite_owner")
    friend, user_friend = await make_player(db_session, username="sim_invite_friend")
    username_owner, username_friend, friend_id = (
        user_owner.username,
        user_friend.username,
        str(user_friend.id),
    )
    await _befriend(owner, friend, username_owner, username_friend)

    room = (await owner.post("/sim-rooms")).json()
    resp = await owner.post(f"/sim-rooms/{room['id']}/invites", json={"friend_user_id": friend_id})
    assert resp.status_code == 201
    assert resp.json()["invite_code"] == room["invite_code"]
    assert resp.json()["owner_username"] == username_owner

    invites = (await friend.get("/sim-rooms/invites")).json()
    assert len(invites) == 1
    assert invites[0]["sim_room_id"] == room["id"]
    assert invites[0]["owner_username"] == username_owner

    # The inviting owner's own invite list should not show it (they're not the invitee).
    assert (await owner.get("/sim-rooms/invites")).json() == []


async def test_invite_a_non_friend_returns_404(client, db_session):
    owner, _ = await make_player(db_session, username="sim_invite_notfriend_owner")
    _, stranger = await make_player(db_session, username="sim_invite_notfriend_stranger")
    stranger_id = str(stranger.id)

    room = (await owner.post("/sim-rooms")).json()
    resp = await owner.post(
        f"/sim-rooms/{room['id']}/invites", json={"friend_user_id": stranger_id}
    )
    assert resp.status_code == 404


async def test_invite_by_non_owner_returns_403(client, db_session):
    owner, _ = await make_player(db_session, username="sim_invite_forbidden_owner")
    other, user_other = await make_player(db_session, username="sim_invite_forbidden_other")
    friend, user_friend = await make_player(db_session, username="sim_invite_forbidden_friend")
    username_other, username_friend, friend_id = (
        user_other.username,
        user_friend.username,
        str(user_friend.id),
    )
    await _befriend(other, friend, username_other, username_friend)

    room = (await owner.post("/sim-rooms")).json()
    resp = await other.post(f"/sim-rooms/{room['id']}/invites", json={"friend_user_id": friend_id})
    assert resp.status_code == 403


async def test_duplicate_invite_returns_409(client, db_session):
    owner, user_owner = await make_player(db_session, username="sim_invite_dup_owner")
    friend, user_friend = await make_player(db_session, username="sim_invite_dup_friend")
    username_owner, username_friend, friend_id = (
        user_owner.username,
        user_friend.username,
        str(user_friend.id),
    )
    await _befriend(owner, friend, username_owner, username_friend)

    room = (await owner.post("/sim-rooms")).json()
    resp1 = await owner.post(f"/sim-rooms/{room['id']}/invites", json={"friend_user_id": friend_id})
    assert resp1.status_code == 201
    resp2 = await owner.post(f"/sim-rooms/{room['id']}/invites", json={"friend_user_id": friend_id})
    assert resp2.status_code == 409


async def test_invite_disappears_from_list_once_room_starts(client, db_session):
    owner, user_owner = await make_player(db_session, username="sim_invite_started_owner")
    friend, user_friend = await make_player(db_session, username="sim_invite_started_friend")
    username_owner, username_friend, friend_id = (
        user_owner.username,
        user_friend.username,
        str(user_friend.id),
    )
    await _befriend(owner, friend, username_owner, username_friend)

    room = (await owner.post("/sim-rooms")).json()
    await owner.post(f"/sim-rooms/{room['id']}/invites", json={"friend_user_id": friend_id})

    owner_bot = await _create_automaton(owner, "OwnerBot")
    friend_bot = await _create_automaton(friend, "FriendBot")
    await owner.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": owner_bot}
    )
    await friend.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": friend_bot}
    )
    await owner.post(f"/sim-rooms/{room['id']}/start")

    assert (await friend.get("/sim-rooms/invites")).json() == []


async def test_non_owner_leaving_removes_only_their_own_entries(client, db_session):
    owner, _ = await make_player(db_session, username="sim_leave_nonowner_owner")
    guest, _ = await make_player(db_session, username="sim_leave_nonowner_guest")

    room = (await owner.post("/sim-rooms")).json()
    owner_bot = await _create_automaton(owner, "OwnerBot")
    guest_bot = await _create_automaton(guest, "GuestBot")
    await owner.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": owner_bot}
    )
    await guest.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": guest_bot}
    )

    resp = await guest.post(f"/sim-rooms/{room['id']}/leave")
    assert resp.status_code == 200
    assert resp.json() == {"room_closed": False, "new_owner_user_id": None}

    state = (await owner.get(f"/sim-rooms/{room['id']}")).json()
    assert state["owner_user_id"] == room["owner_user_id"]
    assert [e["automaton_id"] for e in state["entries"]] == [owner_bot]


async def test_owner_leaving_with_remaining_entrants_transfers_ownership(client, db_session):
    owner, _ = await make_player(db_session, username="sim_leave_transfer_owner")
    guest, user_guest = await make_player(db_session, username="sim_leave_transfer_guest")
    guest_id = str(user_guest.id)

    room = (await owner.post("/sim-rooms")).json()
    owner_bot = await _create_automaton(owner, "OwnerBot")
    guest_bot = await _create_automaton(guest, "GuestBot")
    await owner.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": owner_bot}
    )
    await guest.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": guest_bot}
    )

    resp = await owner.post(f"/sim-rooms/{room['id']}/leave")
    assert resp.status_code == 200
    assert resp.json() == {"room_closed": False, "new_owner_user_id": guest_id}

    state = (await guest.get(f"/sim-rooms/{room['id']}")).json()
    assert state["owner_user_id"] == guest_id
    assert [e["automaton_id"] for e in state["entries"]] == [guest_bot]

    # The new owner can now do owner-only things, like starting the room -
    # but there's only one entrant left, so it correctly still needs another.
    start_resp = await guest.post(f"/sim-rooms/{room['id']}/start")
    assert start_resp.status_code == 400  # too few entrants, not "not owner"


async def test_owner_leaving_alone_closes_the_room(client, db_session):
    owner, _ = await make_player(db_session, username="sim_leave_alone_owner")
    room = (await owner.post("/sim-rooms")).json()
    owner_bot = await _create_automaton(owner)
    await owner.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": owner_bot}
    )

    resp = await owner.post(f"/sim-rooms/{room['id']}/leave")
    assert resp.status_code == 200
    assert resp.json() == {"room_closed": True, "new_owner_user_id": None}

    get_resp = await owner.get(f"/sim-rooms/{room['id']}")
    assert get_resp.status_code == 404


async def test_owner_never_joined_leaving_alone_still_closes_the_room(client, db_session):
    owner, _ = await make_player(db_session, username="sim_leave_neverjoined_owner")
    room = (await owner.post("/sim-rooms")).json()

    resp = await owner.post(f"/sim-rooms/{room['id']}/leave")
    assert resp.status_code == 200
    assert resp.json() == {"room_closed": True, "new_owner_user_id": None}


async def test_leaving_with_multiple_own_automata_removes_all_of_them(client, db_session):
    owner, _ = await make_player(db_session, username="sim_leave_multi_owner")
    guest, _ = await make_player(db_session, username="sim_leave_multi_guest")

    room = (await owner.post("/sim-rooms")).json()
    owner_bot_a = await _create_automaton(owner, "OwnerBotA")
    owner_bot_b = await _create_automaton(owner, "OwnerBotB")
    guest_bot = await _create_automaton(guest, "GuestBot")
    await owner.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": owner_bot_a}
    )
    await owner.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": owner_bot_b}
    )
    await guest.post(
        "/sim-rooms/join", json={"code": room["invite_code"], "automaton_id": guest_bot}
    )

    resp = await owner.post(f"/sim-rooms/{room['id']}/leave")
    assert resp.status_code == 200

    state = (await guest.get(f"/sim-rooms/{room['id']}")).json()
    assert [e["automaton_id"] for e in state["entries"]] == [guest_bot]


async def test_leave_nonexistent_room_returns_404(client, db_session):
    owner, _ = await make_player(db_session, username="sim_leave_missing")
    resp = await owner.post("/sim-rooms/00000000-0000-0000-0000-000000000000/leave")
    assert resp.status_code == 404


# No automated WebSocket test here - see TODO.md "WebSocket endpoints are
# untested" for why: httpx.ASGITransport doesn't implement the WS upgrade
# handshake at all (a GET to a ws-only route just 404s, confirmed while
# attempting this), and Starlette's TestClient (which does support WS) runs
# the app in a separate thread/event loop, which would break this suite's
# shared savepoint-bound AsyncSession (asyncpg connections aren't safe to use
# across event loops). The HTTP side of every flow (join/start/etc.) that
# would trigger a WS push is still fully covered above.
