"""The social graph (FriendRequest, Friend) and the two-tier friend-visibility
system (CLAUDE.md S2 "Friend visibility: confirmed two-tier system"): a
per-player global default (FriendSettings + its allow-list join table
FriendSettingsAutomaton) and a per-friendship override that fully replaces
the global setting in either direction (FriendVisibilityOverride + its
allow-list join table FriendVisibilityOverrideAutomaton).
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from grudge_backend.models.base import Base, CreatedAtMixin, TimestampMixin, UUIDPKMixin


class FriendRequest(UUIDPKMixin, CreatedAtMixin, Base):
    """No status column and no `updated_at` - a row's mere existence IS its
    pending state. Accept/decline/cancel all DELETE the row (accept also
    inserts the Friend pair in the same flush) - this is what lets someone
    re-request after a decline without fighting a DB uniqueness constraint;
    the service layer checks for an existing pending row in either direction
    before inserting a new one instead.
    """

    __tablename__ = "friend_requests"
    __table_args__ = (
        CheckConstraint("from_user_id <> to_user_id", name="ck_friend_requests_not_self"),
        Index("ix_friend_requests_from_user", "from_user_id"),
        Index("ix_friend_requests_to_user", "to_user_id"),
    )

    from_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    to_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


class Friend(UUIDPKMixin, CreatedAtMixin, Base):
    """Symmetric: created as a PAIR of rows (one per direction) when a
    request is accepted, both deleted together on unfriend - an app-layer
    invariant, not DB-enforced (no FK ties the two directions together),
    same philosophy as FolderCycleError being an app-layer-only guard.
    """

    __tablename__ = "friends"
    __table_args__ = (
        CheckConstraint("user_id <> friend_user_id", name="ck_friends_not_self"),
        UniqueConstraint("user_id", "friend_user_id", name="uq_friends_user_friend"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    friend_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


class FriendSettings(UUIDPKMixin, TimestampMixin, Base):
    """Per-player global default automaton visibility. Lazily created - no
    row exists until the player's first PATCH (or the share-with-friends
    hook at automaton-creation time); GET computes the "hide" default when
    absent, per CLAUDE.md's "defaults to Hide... sharing is opt-in" rule.
    """

    __tablename__ = "friend_settings"
    __table_args__ = (UniqueConstraint("user_id", name="uq_friend_settings_user"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    global_mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default="hide")


class FriendSettingsAutomaton(UUIDPKMixin, CreatedAtMixin, Base):
    """The global "specific" allow-list. FKs directly to `users.id`, NOT
    through `friend_settings.id` (unlike FriendVisibilityOverrideAutomaton
    below) - the automaton-creation "share with friends" checkbox must be
    able to write here unconditionally, possibly before any FriendSettings
    row exists for that player. FKing through friend_settings.id would force
    a silent get-or-create of a settings row the player never asked for,
    just to hang a join row off it.
    """

    __tablename__ = "friend_settings_automata"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "automaton_id", name="uq_friend_settings_automata_user_automaton"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    automaton_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automata.id", ondelete="CASCADE"), nullable=False
    )


class FriendVisibilityOverride(UUIDPKMixin, TimestampMixin, Base):
    """Per-friendship override. `user_id` is whose override this is (the
    settings owner); `friend_user_id` is which friend it applies to. Lazily
    created, same as FriendSettings - every friendship implicitly starts at
    "default" (inherit global) until explicitly touched.
    """

    __tablename__ = "friend_visibility_overrides"
    __table_args__ = (
        CheckConstraint(
            "user_id <> friend_user_id", name="ck_friend_visibility_overrides_not_self"
        ),
        UniqueConstraint(
            "user_id", "friend_user_id", name="uq_friend_visibility_overrides_user_friend"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    friend_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default="default")


class FriendVisibilityOverrideAutomaton(UUIDPKMixin, CreatedAtMixin, Base):
    """Per-friendship "specific" allow-list. Safe to FK through the parent
    override's id (unlike FriendSettingsAutomaton above) - the share-with-
    friends hook only ever touches overrides already in "specific" mode,
    which are guaranteed to exist by the time this table is written to.
    """

    __tablename__ = "friend_visibility_override_automata"
    __table_args__ = (
        UniqueConstraint(
            "override_id",
            "automaton_id",
            name="uq_friend_visibility_override_automata_override_automaton",
        ),
    )

    override_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("friend_visibility_overrides.id", ondelete="CASCADE"),
        nullable=False,
    )
    automaton_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automata.id", ondelete="CASCADE"), nullable=False
    )
