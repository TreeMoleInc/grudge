from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from grudge_backend.models.base import Base, CreatedAtMixin, UUIDPKMixin


class Notification(UUIDPKMixin, CreatedAtMixin, Base):
    """Durable per-user notification store (CLAUDE.md S2/Phase 6) - closes the
    gap where the live "automaton flagged" WebSocket push
    (services/progress_relay.py's notify_automaton_flagged) silently reaches
    nobody if the owner isn't connected to that tournament's channel at the
    exact moment it fires. `type` is a plain string discriminator
    ("automaton_flagged" is the only value today, mirroring
    waiting_rooms.room_type's precedent) - scoped narrowly to this one use
    case, not a general notification platform. `read_at` (not
    deletion-as-state, unlike sim_room_invites) - a notification should remain
    visible as history after being seen, since the whole point here is
    durability. `user_id` is CASCADE (private per-user list, same reasoning as
    RatingHistory). `tournament_id`/`automaton_id` are SET NULL, consistent
    with TournamentEntry - `automaton_name` is a snapshot column so the row
    stays meaningful even after the automaton is deleted.
    """

    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    tournament_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="SET NULL"), nullable=True
    )
    automaton_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automata.id", ondelete="SET NULL"), nullable=True
    )
    automaton_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
