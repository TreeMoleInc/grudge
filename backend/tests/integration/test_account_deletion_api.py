"""DELETE /me - account deletion. Confirmed design (CLAUDE.md S2, 2026-08-30):
hard-delete the user row (the FK cascade network does almost everything -
automata, sessions, friendships, auth identities), but tournament/match
history survives with the player's name replaced by a distinguishable
anonymized label, since entrants[] is a frozen snapshot, not a live join.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from grudge_backend.models.automaton import Automaton, AutomatonVersion
from grudge_backend.models.folder import AutomatonFolder
from grudge_backend.models.friend import Friend, FriendRequest
from grudge_backend.models.session import Session as SessionModel
from grudge_backend.models.tournament import Tournament, TournamentEntry
from grudge_backend.models.user import AuthIdentity, User
from tests.conftest import make_player

pytestmark = pytest.mark.integration

_COOPERATE_CODE = "def decide(history):\n    return COOPERATE\n"


async def test_deleting_account_removes_the_user_row(client, db_session):
    player, user = await make_player(db_session, username="deleter_alice")
    resp = await player.delete("/me")
    assert resp.status_code == 204

    result = await db_session.execute(select(User).where(User.id == user.id))
    assert result.scalar_one_or_none() is None


async def test_deleting_account_logs_out_the_session(client, db_session):
    player, _user = await make_player(db_session, username="deleter_bob")
    resp = await player.delete("/me")
    assert resp.status_code == 204

    me_resp = await player.get("/me")
    assert me_resp.status_code == 401


async def test_deleting_account_cascades_automata_versions_and_folders(client, db_session):
    player, _user = await make_player(db_session, username="deleter_carol")
    folder_resp = await player.post("/folders", json={"name": "My folder"})
    folder_id = folder_resp.json()["id"]
    bot_resp = await player.post(
        "/automata", json={"name": "Bot", "code": _COOPERATE_CODE, "folder_id": folder_id}
    )
    automaton_id = bot_resp.json()["id"]

    resp = await player.delete("/me")
    assert resp.status_code == 204

    assert (
        await db_session.execute(select(Automaton).where(Automaton.id == automaton_id))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(
            select(AutomatonVersion).where(AutomatonVersion.automaton_id == automaton_id)
        )
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(AutomatonFolder).where(AutomatonFolder.id == folder_id))
    ).scalar_one_or_none() is None


async def test_deleting_account_removes_auth_identities_and_sessions(client, db_session):
    player, user = await make_player(db_session, username="deleter_dave")
    db_session.add(
        AuthIdentity(
            user_id=user.id,
            provider="google",
            provider_user_id="123",
            provider_email="d@example.com",
        )
    )
    await db_session.flush()

    resp = await player.delete("/me")
    assert resp.status_code == 204

    assert (
        await db_session.execute(select(AuthIdentity).where(AuthIdentity.user_id == user.id))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(SessionModel).where(SessionModel.user_id == user.id))
    ).scalar_one_or_none() is None


async def test_deleting_account_breaks_friendships_both_directions(client, db_session):
    player, user = await make_player(db_session, username="deleter_erin")
    _friend_player, friend_user = await make_player(db_session, username="erins_friend")

    db_session.add(Friend(user_id=user.id, friend_user_id=friend_user.id))
    db_session.add(Friend(user_id=friend_user.id, friend_user_id=user.id))
    await db_session.flush()

    resp = await player.delete("/me")
    assert resp.status_code == 204

    remaining = await db_session.execute(
        select(Friend).where(
            (Friend.user_id == friend_user.id) | (Friend.friend_user_id == friend_user.id)
        )
    )
    assert remaining.scalars().all() == []


async def test_deleting_account_removes_pending_friend_requests(client, db_session):
    player, user = await make_player(db_session, username="deleter_frank")
    _other_player, other_user = await make_player(db_session, username="franks_pending_friend")

    db_session.add(FriendRequest(from_user_id=user.id, to_user_id=other_user.id))
    await db_session.flush()

    resp = await player.delete("/me")
    assert resp.status_code == 204

    remaining = await db_session.execute(
        select(FriendRequest).where(FriendRequest.to_user_id == other_user.id)
    )
    assert remaining.scalars().all() == []


async def test_completed_tournament_history_survives_with_anonymized_name(client, db_session):
    player, user = await make_player(db_session, username="deleter_grace")
    tournament = Tournament(
        type="sim",
        status="completed",
        entrants=[
            {
                "user_id": str(user.id),
                "automaton_id": "a",
                "automaton_name": "Grace's Bot",
                "owner_username": "deleter_grace",
                "code_snapshot": _COOPERATE_CODE,
                "rating_snapshot": 1000,
            },
            {
                "user_id": "00000000-0000-0000-0000-000000000099",
                "automaton_id": "b",
                "automaton_name": "Someone Else's Bot",
                "owner_username": "still_here",
                "code_snapshot": _COOPERATE_CODE,
                "rating_snapshot": 1000,
            },
        ],
    )
    db_session.add(tournament)
    await db_session.flush()
    tournament_id = tournament.id

    resp = await player.delete("/me")
    assert resp.status_code == 204

    result = await db_session.execute(select(Tournament).where(Tournament.id == tournament_id))
    surviving = result.scalar_one()
    entrants_by_automaton = {e["automaton_id"]: e for e in surviving.entrants}

    deleted_entrant = entrants_by_automaton["a"]
    assert deleted_entrant["owner_username"] == f"[user-deleted-{str(user.id)[:8]}]"
    assert deleted_entrant["owner_username"] != "deleter_grace"
    # Everything else about their entry is untouched.
    assert deleted_entrant["automaton_name"] == "Grace's Bot"
    assert deleted_entrant["code_snapshot"] == _COOPERATE_CODE
    assert deleted_entrant["rating_snapshot"] == 1000

    # The OTHER entrant in the same tournament is completely untouched.
    other_entrant = entrants_by_automaton["b"]
    assert other_entrant["owner_username"] == "still_here"


async def test_two_deleted_accounts_get_distinguishable_labels(client, db_session):
    player_a, user_a = await make_player(db_session, username="deleter_henry")
    _player_b, user_b = await make_player(db_session, username="deleter_iris")
    tournament = Tournament(
        type="sim",
        status="completed",
        entrants=[
            {"user_id": str(user_a.id), "automaton_id": "a", "owner_username": "deleter_henry"},
            {"user_id": str(user_b.id), "automaton_id": "b", "owner_username": "deleter_iris"},
        ],
    )
    db_session.add(tournament)
    await db_session.flush()
    tournament_id = tournament.id

    assert (await player_a.delete("/me")).status_code == 204

    # user_b hasn't been deleted - only user_a's entrant should be anonymized.
    result = await db_session.execute(select(Tournament).where(Tournament.id == tournament_id))
    entrants_by_automaton = {e["automaton_id"]: e for e in result.scalar_one().entrants}
    assert entrants_by_automaton["a"]["owner_username"] == f"[user-deleted-{str(user_a.id)[:8]}]"
    assert entrants_by_automaton["b"]["owner_username"] == "deleter_iris"


async def test_deletion_is_blocked_while_waiting_in_matchmaking_queue(client, db_session):
    player, user = await make_player(db_session, username="deleter_blocked_queue")
    bot_resp = await player.post("/automata", json={"name": "Bot", "code": _COOPERATE_CODE})
    await player.post("/matchmaking/unranked/join", json={"automaton_id": bot_resp.json()["id"]})

    resp = await player.delete("/me")
    assert resp.status_code == 409

    assert (
        await db_session.execute(select(User).where(User.id == user.id))
    ).scalar_one_or_none() is not None


async def test_deletion_is_blocked_while_in_an_open_sim_room(client, db_session):
    player, user = await make_player(db_session, username="deleter_blocked_room")
    bot_resp = await player.post("/automata", json={"name": "Bot", "code": _COOPERATE_CODE})
    room_resp = await player.post("/sim-rooms")
    await player.post(
        "/sim-rooms/join",
        json={"code": room_resp.json()["invite_code"], "automaton_id": bot_resp.json()["id"]},
    )

    resp = await player.delete("/me")
    assert resp.status_code == 409

    assert (
        await db_session.execute(select(User).where(User.id == user.id))
    ).scalar_one_or_none() is not None


async def test_deletion_is_blocked_while_owning_an_open_room_with_no_entry_of_your_own(
    client, db_session
):
    # 2026-09-15 fix: creating a room doesn't auto-add an entry for the owner
    # (see services/sim_rooms.py) - the check above alone (entrant in an open
    # room) missed an owner who invited others but never entered their own
    # automaton. Without this, deleting them would CASCADE the SimRoom away
    # via owner_user_id, which CASCADEs every OTHER player's SimRoomEntry
    # with it - destroying their room state instead of transferring
    # ownership per CLAUDE.md's confirmed rule.
    owner, owner_user = await make_player(db_session, username="deleter_owns_empty_room")
    other, _ = await make_player(db_session, username="other_in_owners_room")
    room_resp = await owner.post("/sim-rooms")
    other_bot = await other.post("/automata", json={"name": "Bot", "code": _COOPERATE_CODE})
    await other.post(
        "/sim-rooms/join",
        json={
            "code": room_resp.json()["invite_code"],
            "automaton_id": other_bot.json()["id"],
        },
    )

    resp = await owner.delete("/me")
    assert resp.status_code == 409

    assert (
        await db_session.execute(select(User).where(User.id == owner_user.id))
    ).scalar_one_or_none() is not None


async def test_deletion_is_blocked_while_entrant_in_a_running_tournament(client, db_session):
    player, user = await make_player(db_session, username="deleter_blocked_running")
    tournament = Tournament(
        type="sim",
        status="running",
        entrants=[
            {
                "user_id": str(user.id),
                "automaton_id": "a",
                "owner_username": "deleter_blocked_running",
            }
        ],
    )
    db_session.add(tournament)
    await db_session.flush()

    resp = await player.delete("/me")
    assert resp.status_code == 409

    assert (
        await db_session.execute(select(User).where(User.id == user.id))
    ).scalar_one_or_none() is not None


async def test_relational_tournament_entries_get_anonymized_too(client, db_session):
    """The relational tournament_entries mirror of entrants[] (Phase 6) needs
    the exact same anonymization step as the JSONB blob above - user_id is
    SET NULL (not CASCADE) specifically so this row survives, but
    owner_username is a plain snapshot column that wouldn't update itself
    just because user_id goes to NULL.
    """
    player, user = await make_player(db_session, username="deleter_relational_jane")
    tournament = Tournament(type="sim", status="completed", entrants=[])
    db_session.add(tournament)
    await db_session.flush()
    entry = TournamentEntry(
        tournament_id=tournament.id,
        user_id=user.id,
        automaton_id=None,
        rating_snapshot=1000,
        automaton_name="Jane's Bot",
        owner_username="deleter_relational_jane",
    )
    db_session.add(entry)
    await db_session.flush()
    entry_id = entry.id

    resp = await player.delete("/me")
    assert resp.status_code == 204

    db_session.expire_all()  # the FK's SET NULL fired in Postgres, not through this session
    result = await db_session.execute(select(TournamentEntry).where(TournamentEntry.id == entry_id))
    surviving = result.scalar_one()
    assert surviving.owner_username == f"[user-deleted-{str(user.id)[:8]}]"
    assert surviving.user_id is None  # SET NULL fired
    assert surviving.automaton_name == "Jane's Bot"  # untouched


async def test_deletion_requires_authentication(client, db_session):
    resp = await client.delete("/me")
    assert resp.status_code == 401
