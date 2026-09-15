from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from grudge_backend.models.base import Base, CreatedAtMixin, UUIDPKMixin


class WaitingRoom(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "waiting_rooms"

    room_type: Mapped[str] = mapped_column(String(16), nullable=False)  # ranked | unranked
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")
    tournament_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="SET NULL"), nullable=True
    )


class MatchmakingQueueEntry(UUIDPKMixin, Base):
    """One player's automaton waiting for a match. `rating_snapshot` is captured
    at join time (not re-read live) so a room's spread-bound check stays stable
    for the lifetime of the room, matching the "no re-validation/ejection later"
    property CLAUDE.md's matchmaking design relies on. `last_heartbeat_at`
    backs the ~30s presence-eviction sweep (CLAUDE.md S2, extended here to
    ranked as well as unranked - see TODO.md).
    """

    __tablename__ = "matchmaking_queue_entries"
    __table_args__ = (
        Index(
            "uq_matchmaking_queue_entries_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'waiting'"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    automaton_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automata.id", ondelete="CASCADE"), nullable=False
    )
    queue_type: Mapped[str] = mapped_column(String(16), nullable=False)  # ranked | unranked
    rating_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="waiting")
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waiting_rooms.id", ondelete="SET NULL"), nullable=True
    )
