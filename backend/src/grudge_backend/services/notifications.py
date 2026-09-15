"""Durable per-user notification store (CLAUDE.md S2/Phase 6), scoped exactly
to the "automaton flagged" case - see models/notification.py's docstring for
the full rationale. This is a second, independent delivery path fed from the
same in-scope worker data as the existing live WS push
(services/progress_relay.py's notify_automaton_flagged), not a variant of
it - that live push stays exactly as it is.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from grudge_engine.results import TournamentResult
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.models.notification import Notification
from grudge_backend.models.tournament import Tournament

AUTOMATON_FLAGGED = "automaton_flagged"


class NotificationNotFoundError(Exception):
    pass


async def create_flagged_notifications(
    db: AsyncSession, *, tournament: Tournament, result: TournamentResult, entrants: list[dict]
) -> None:
    entrant_by_automaton = {e["automaton_id"]: e for e in entrants}
    for faulted in result.faulted:
        entrant = entrant_by_automaton.get(faulted.automaton_id)
        if entrant is None or entrant.get("user_id") is None:
            continue
        db.add(
            Notification(
                user_id=uuid.UUID(entrant["user_id"]),
                type=AUTOMATON_FLAGGED,
                tournament_id=tournament.id,
                automaton_id=uuid.UUID(faulted.automaton_id),
                automaton_name=entrant.get("automaton_name"),
                reason=faulted.reason,
            )
        )
    await db.flush()


async def list_for_user(
    db: AsyncSession, *, user_id: uuid.UUID, limit: int = 50
) -> list[Notification]:
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def mark_read(db: AsyncSession, *, notification_id: uuid.UUID, user_id: uuid.UUID) -> None:
    notification = await db.get(Notification, notification_id)
    if notification is None or notification.user_id != user_id:
        raise NotificationNotFoundError("Notification not found.")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        await db.flush()


async def mark_all_read(db: AsyncSession, *, user_id: uuid.UUID) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
