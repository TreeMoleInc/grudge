from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from grudge_backend.models.base import Base, CreatedAtMixin, UUIDPKMixin


class Job(UUIDPKMixin, CreatedAtMixin, Base):
    """Generic background-job queue row - not tournament-specific (CLAUDE.md
    frames "a jobs table + a background worker loop" as general infrastructure).
    Only `job_type="tournament"` exists today. `heartbeat_at` is ticked by the
    worker ~every 5s while actively processing; the watchdog process (a
    separate process, not the worker) scans for `status="running"` rows whose
    heartbeat has gone stale (>30s) and fails them - this is what catches both
    a single hung job and the whole worker process dying, without needing to
    distinguish which.
    """

    __tablename__ = "jobs"

    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="queued")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
