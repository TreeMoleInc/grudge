from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from grudge_backend.models.base import Base, CreatedAtMixin, UUIDPKMixin


class Tournament(UUIDPKMixin, CreatedAtMixin, Base):
    """`entrants`/`result` (JSON) remain the source the Results page renders
    from, unchanged since Phase 3 - `TournamentEntry`/`Match` below (Phase 6)
    are an ADDITIVE relational layer populated alongside, not a replacement,
    specifically so cross-tournament queries ("every match between these two
    players") don't require scanning JSON. `entrants` is captured once, at
    start time, and MUST include a frozen `code_snapshot` per player -
    automaton_versions are mutable save-slots (CLAUDE.md S2), so snapshotting
    late would let a player's later edits corrupt what should be immutable
    history. `result` is the serialized grudge_engine.results.TournamentResult
    once the worker finishes.
    """

    __tablename__ = "tournaments"

    type: Mapped[str] = mapped_column(String(16), nullable=False)  # ranked | unranked | sim
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    entrants: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TournamentEntry(UUIDPKMixin, CreatedAtMixin, Base):
    """Relational mirror of one entry in `tournaments.entrants` (Phase 6) - a
    query-optimized, ADDITIVE layer, not a replacement (see `Tournament`'s
    docstring). `user_id`/`automaton_id`/`automaton_version_id` are SET NULL on
    delete, deliberately NOT CASCADE: `tournaments.entrants`'s JSONB blob
    already survives account deletion by design (anonymized in place, per
    CLAUDE.md S2's account-deletion decision) specifically so match history
    outlives the account - cascading here would silently contradict that. The
    snapshot columns (code_snapshot/rating_snapshot/automaton_name/
    owner_username/automaton_version_name) mirror `entrants`'s shape exactly so
    a row stays meaningful after any of its parents are gone, and
    `owner_username` gets the same anonymization rewrite `entrants` does on
    account deletion (see services/account.py).
    """

    __tablename__ = "tournament_entries"
    __table_args__ = (
        UniqueConstraint(
            "tournament_id", "automaton_id", name="uq_tournament_entries_tournament_automaton"
        ),
    )

    tournament_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    automaton_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automata.id", ondelete="SET NULL"), nullable=True
    )
    automaton_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automaton_versions.id", ondelete="SET NULL"), nullable=True
    )
    code_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    automaton_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    automaton_version_name: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Match(UUIDPKMixin, CreatedAtMixin, Base):
    """Relational mirror of one entry in `tournaments.result["matches"]`
    (Phase 6) - additive, see `Tournament`'s docstring. `rounds` deliberately
    stays JSONB rather than one row per round: a single match can run up to
    1500 rounds (MAX_LENGTH), so per-round rows would be a real row-count
    explosion for data the 2026-08-30 log-retention audit (CLAUDE.md S2)
    already measured compresses extremely well as JSONB (10-20x via TOAST).
    This does mean the round log exists in both `tournaments.result` and here
    - deliberate, not drift-prone, since both are written atomically from the
    same immutable TournamentResult in the same worker transaction.
    """

    __tablename__ = "matches"

    tournament_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False
    )
    automaton_a_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automata.id", ondelete="SET NULL"), nullable=True
    )
    automaton_b_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automata.id", ondelete="SET NULL"), nullable=True
    )
    games_played: Mapped[int] = mapped_column(Integer, nullable=False)
    score_a: Mapped[int] = mapped_column(Integer, nullable=False)
    score_b: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # completed | voided
    voided_side: Mapped[str | None] = mapped_column(String(8), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rounds: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
