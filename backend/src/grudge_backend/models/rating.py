from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from grudge_backend.models.base import Base, CreatedAtMixin, UUIDPKMixin


class RatingHistory(UUIDPKMixin, CreatedAtMixin, Base):
    """One row per player per ranked tournament (CLAUDE.md S2: "kept for
    auditability/debugging of the Elo math, not just the current value") -
    written by services/rating.py's apply_rating_update, in the same worker
    transaction that marks the tournament completed. `user_id` is CASCADE,
    deliberately unlike TournamentEntry's SET NULL - this table is a private
    per-user audit trail nobody else's query ever reads, not a piece of shared
    match history, so there's no reason for it to survive account deletion and
    no anonymization step is needed for it.
    """

    __tablename__ = "rating_history"
    __table_args__ = (
        UniqueConstraint("tournament_id", "user_id", name="uq_rating_history_tournament_user"),
    )

    tournament_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating_before: Mapped[int] = mapped_column(Integer, nullable=False)
    rating_after: Mapped[int] = mapped_column(Integer, nullable=False)
    delta: Mapped[float] = mapped_column(Float, nullable=False)
    k_used: Mapped[int] = mapped_column(Integer, nullable=False)
    e_i: Mapped[float] = mapped_column(Float, nullable=False)
    s_i: Mapped[float] = mapped_column(Float, nullable=False)
    ranked_tournaments_played_before: Mapped[int] = mapped_column(Integer, nullable=False)
