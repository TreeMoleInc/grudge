from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from grudge_backend.models.base import Base, CreatedAtMixin, UUIDPKMixin


class Session(UUIDPKMixin, CreatedAtMixin, Base):
    """A logged-in session. Auth infra, not part of CLAUDE.md's product data-model
    sketch. `token_hash` is a SHA-256 hex digest of the raw cookie value - the raw
    token itself is never persisted.

    `ix_sessions_last_seen` (Phase 7 perf pass, 2026-09-02): backs
    services/stats.py's `get_live_stats`, which filters on `last_seen_at` +
    `expires_at` - the one query in the whole app guaranteed to run from
    every visitor (logged in or not, GET /stats/live is deliberately
    unauthenticated) on a 20s poll. `last_seen_at` leads the composite since
    it's the more selective predicate (a 120s window) vs `expires_at` (true
    for nearly every non-expired row) - without this, that query was a full
    table scan on every poll, on a table this file's own history already
    flagged as prone to unbounded growth before the 2026-08-30 expired-session
    sweep (auth/session.py's sweep_expired_sessions) was added.
    """

    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_last_seen", "last_seen_at", "expires_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
