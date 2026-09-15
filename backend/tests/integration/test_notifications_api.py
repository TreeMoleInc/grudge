"""Durable notification store (CLAUDE.md S2/Phase 6) - the durable counterpart
to the existing live "automaton flagged" WebSocket push. Covers both the real
worker wiring (a faulted automaton creates a Notification row) and the REST
surface (list/mark-read/mark-all-read).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from grudge_backend.models.notification import Notification
from grudge_backend.services.jobs import claim_next_job
from grudge_backend.worker import process_job
from tests.conftest import make_player
from tests.integration.test_worker import (
    _ALWAYS_COOPERATE,
    _BROKEN,
    _entrant,
    _make_tournament_and_job,
)

pytestmark = pytest.mark.integration


async def test_faulted_automaton_creates_a_durable_notification(
    client, db_session, worker_session_maker
):
    allc = await _entrant(db_session, name="allc", code=_ALWAYS_COOPERATE)
    broken = await _entrant(db_session, name="broken", code=_BROKEN)
    tournament = await _make_tournament_and_job(db_session, entrants=[allc, broken], seed=1)

    await process_job(await claim_next_job(db_session), session_maker=worker_session_maker)

    result = await db_session.execute(
        select(Notification).where(Notification.tournament_id == tournament.id)
    )
    notifications = result.scalars().all()
    assert len(notifications) == 1
    notification = notifications[0]
    assert str(notification.user_id) == broken["user_id"]
    assert str(notification.automaton_id) == broken["automaton_id"]
    assert notification.automaton_name == "broken"
    assert notification.type == "automaton_flagged"
    assert notification.reason  # a real, non-empty reason from the engine
    assert notification.read_at is None


async def test_list_notifications_is_newest_first_and_scoped_to_the_caller(client, db_session):
    # created_at is set explicitly (not left to the server_default) because
    # Postgres's now() is transaction-time, not statement-time - two rows
    # inserted in the same test transaction would otherwise get an identical
    # timestamp, making "newest first" genuinely ambiguous to assert on.
    player, user = await make_player(db_session, username="notif_owner")
    _other_player, other_user = await make_player(db_session, username="notif_not_owner")

    older = Notification(
        user_id=user.id,
        type="automaton_flagged",
        reason="older",
        automaton_name="Bot A",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    db_session.add(older)
    await db_session.flush()
    newer = Notification(
        user_id=user.id,
        type="automaton_flagged",
        reason="newer",
        automaton_name="Bot B",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    db_session.add(newer)
    db_session.add(
        Notification(
            user_id=other_user.id,
            type="automaton_flagged",
            reason="not yours",
            automaton_name="Bot C",
        )
    )
    await db_session.commit()

    resp = await player.get("/notifications")
    assert resp.status_code == 200
    body = resp.json()
    assert [n["reason"] for n in body] == ["newer", "older"]


async def test_mark_notification_read(client, db_session):
    player, user = await make_player(db_session, username="notif_reader")
    notification = Notification(
        user_id=user.id, type="automaton_flagged", reason="r", automaton_name="Bot"
    )
    db_session.add(notification)
    await db_session.commit()
    notification_id = notification.id

    resp = await player.post(f"/notifications/{notification_id}/read")
    assert resp.status_code == 204

    list_resp = await player.get("/notifications")
    assert list_resp.json()[0]["read_at"] is not None


async def test_mark_someone_elses_notification_read_returns_404(client, db_session):
    _owner_player, owner_user = await make_player(db_session, username="notif_real_owner")
    intruder_player, _intruder_user = await make_player(db_session, username="notif_intruder")
    notification = Notification(
        user_id=owner_user.id, type="automaton_flagged", reason="r", automaton_name="Bot"
    )
    db_session.add(notification)
    await db_session.commit()

    resp = await intruder_player.post(f"/notifications/{notification.id}/read")
    assert resp.status_code == 404


async def test_mark_all_read_only_touches_the_callers_own_unread_notifications(client, db_session):
    player, user = await make_player(db_session, username="notif_mark_all")
    _other_player, other_user = await make_player(db_session, username="notif_mark_all_other")
    db_session.add(
        Notification(user_id=user.id, type="automaton_flagged", reason="a", automaton_name="Bot")
    )
    db_session.add(
        Notification(user_id=user.id, type="automaton_flagged", reason="b", automaton_name="Bot")
    )
    others = Notification(
        user_id=other_user.id, type="automaton_flagged", reason="c", automaton_name="Bot"
    )
    db_session.add(others)
    await db_session.commit()

    resp = await player.post("/notifications/read-all")
    assert resp.status_code == 204

    list_resp = await player.get("/notifications")
    assert all(n["read_at"] is not None for n in list_resp.json())

    await db_session.refresh(others)
    assert others.read_at is None  # untouched - belongs to a different user
