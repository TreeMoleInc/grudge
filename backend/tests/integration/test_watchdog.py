"""Watchdog stale-job detection and the matchmaking sweeps it shares a
process with (CLAUDE.md S3: heartbeat-based detection, a separate process
from the worker, Discord webhook alerting). The Discord webhook itself is
mocked via respx (same pattern as tests/integration/test_oauth_e2e.py).
`session_maker=worker_session_maker` mirrors worker.py's testability fix -
see that fixture's docstring in conftest.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import respx
from httpx import Response
from sqlalchemy import select

from grudge_backend.config import settings
from grudge_backend.models.job import Job
from grudge_backend.models.session import Session
from grudge_backend.models.tournament import Tournament
from grudge_backend.watchdog import handle_expired_sessions, handle_stale_jobs
from tests.conftest import make_user

pytestmark = pytest.mark.integration


async def test_handle_stale_jobs_fails_job_and_voids_tournament(
    db_session, worker_session_maker, monkeypatch
):
    monkeypatch.setattr(settings, "discord_webhook_url", "")  # alerting off - just the DB effects

    tournament = Tournament(type="ranked", status="running", entrants=[])
    db_session.add(tournament)
    await db_session.flush()

    stale_heartbeat = datetime.now(UTC) - timedelta(seconds=45)  # older than the 30s threshold
    job = Job(
        job_type="tournament",
        status="running",
        payload={"tournament_id": str(tournament.id)},
        heartbeat_at=stale_heartbeat,
    )
    db_session.add(job)
    await db_session.commit()

    await handle_stale_jobs(session_maker=worker_session_maker)

    await db_session.refresh(job)
    await db_session.refresh(tournament)
    assert job.status == "failed"
    assert job.last_error == "stale heartbeat"
    assert tournament.status == "failed_voided"
    assert tournament.error_message is not None


async def test_handle_stale_jobs_ignores_healthy_jobs(
    db_session, worker_session_maker, monkeypatch
):
    monkeypatch.setattr(settings, "discord_webhook_url", "")

    tournament = Tournament(type="ranked", status="running", entrants=[])
    db_session.add(tournament)
    await db_session.flush()

    job = Job(
        job_type="tournament",
        status="running",
        payload={"tournament_id": str(tournament.id)},
        heartbeat_at=datetime.now(UTC),  # fresh
    )
    db_session.add(job)
    await db_session.commit()

    await handle_stale_jobs(session_maker=worker_session_maker)

    await db_session.refresh(job)
    assert job.status == "running"


@respx.mock
async def test_handle_stale_jobs_posts_discord_alert_when_configured(
    db_session, worker_session_maker, monkeypatch
):
    webhook_url = "https://discord.com/api/webhooks/test/token"
    monkeypatch.setattr(settings, "discord_webhook_url", webhook_url)
    route = respx.post(webhook_url).mock(return_value=Response(204))
    # handle_stale_jobs also fires the internal progress-relay HTTP callback
    # (services/progress_relay.py) - @respx.mock asserts every outgoing
    # request is mocked, so that one needs a route too, even though this test
    # only cares about the Discord alert.
    respx.post(url__regex=r".*/internal/tournaments/.*/progress").mock(return_value=Response(204))

    tournament = Tournament(type="ranked", status="running", entrants=[])
    db_session.add(tournament)
    await db_session.flush()

    job = Job(
        job_type="tournament",
        status="running",
        payload={"tournament_id": str(tournament.id)},
        heartbeat_at=datetime.now(UTC) - timedelta(seconds=100),
    )
    db_session.add(job)
    await db_session.commit()

    await handle_stale_jobs(session_maker=worker_session_maker)

    assert route.called


async def test_handle_stale_jobs_is_a_noop_when_nothing_stale(db_session, worker_session_maker):
    # Just proves it doesn't blow up scanning an empty/healthy jobs table.
    await handle_stale_jobs(session_maker=worker_session_maker)


async def test_handle_stale_jobs_with_missing_tournament_does_not_crash(
    db_session, worker_session_maker, monkeypatch
):
    monkeypatch.setattr(settings, "discord_webhook_url", "")
    job = Job(
        job_type="tournament",
        status="running",
        payload={"tournament_id": str(uuid.uuid4())},  # no such tournament row
        heartbeat_at=datetime.now(UTC) - timedelta(seconds=100),
    )
    db_session.add(job)
    await db_session.commit()

    await handle_stale_jobs(session_maker=worker_session_maker)

    await db_session.refresh(job)
    assert job.status == "failed"


async def test_handle_expired_sessions_deletes_only_expired_rows(db_session, worker_session_maker):
    user = await make_user(db_session, username="session_sweep_target")
    now = datetime.now(UTC)
    expired = Session(
        user_id=user.id,
        token_hash=("expired" + "0" * 57)[:64],
        expires_at=now - timedelta(days=1),
        last_seen_at=now - timedelta(days=1),
    )
    still_valid = Session(
        user_id=user.id,
        token_hash=("valid" + "0" * 59)[:64],
        expires_at=now + timedelta(days=1),
        last_seen_at=now,
    )
    db_session.add_all([expired, still_valid])
    await db_session.commit()

    deleted = await handle_expired_sessions(session_maker=worker_session_maker)

    assert deleted == 1
    result = await db_session.execute(select(Session).where(Session.user_id == user.id))
    remaining = result.scalars().all()
    assert len(remaining) == 1
    assert remaining[0].token_hash == still_valid.token_hash


async def test_handle_expired_sessions_is_a_noop_when_nothing_expired(
    db_session, worker_session_maker
):
    deleted = await handle_expired_sessions(session_maker=worker_session_maker)
    assert deleted == 0
