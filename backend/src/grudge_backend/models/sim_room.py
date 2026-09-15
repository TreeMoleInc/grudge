from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from grudge_backend.models.base import Base, CreatedAtMixin, UUIDPKMixin


class SimRoom(UUIDPKMixin, CreatedAtMixin, Base):
    """Code/invite join system (CLAUDE.md S3) - does NOT require exactly 4
    entrants and has no waiting room; whatever's in `sim_room_entries` when the
    owner starts it is the field size (a floor of 2 is enforced at the service
    layer, not the DB - CLAUDE.md doesn't specify a minimum, see TODO.md).
    """

    __tablename__ = "sim_rooms"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    invite_code: Mapped[str] = mapped_column(String(12), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")
    tournament_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="SET NULL"), nullable=True
    )


class SimRoomEntry(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "sim_room_entries"
    __table_args__ = (
        UniqueConstraint("sim_room_id", "automaton_id", name="uq_sim_room_entries_room_automaton"),
    )

    sim_room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sim_rooms.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    automaton_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automata.id", ondelete="CASCADE"), nullable=False
    )


class SimRoomInvite(UUIDPKMixin, CreatedAtMixin, Base):
    """A room owner directly inviting a friend, as an alternative to sharing
    the invite code out-of-band. No realtime notification (consistent with
    Phase 5's no-realtime-for-friends decision, see CLAUDE.md S2) - the
    invited player sees it by opening the Simulate tab, which lists their
    pending invites via a plain GET, same as everything else in the friends
    system. An invite naturally stops being "pending" once its room leaves
    "open" status (started, or - not currently possible - cancelled), so
    listing only joins against still-open rooms rather than needing an
    explicit invite-status column or a cleanup step on start.
    """

    __tablename__ = "sim_room_invites"
    __table_args__ = (
        UniqueConstraint("sim_room_id", "invited_user_id", name="uq_sim_room_invites_room_user"),
    )

    sim_room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sim_rooms.id", ondelete="CASCADE"), nullable=False
    )
    invited_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
