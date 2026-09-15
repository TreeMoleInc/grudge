from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from grudge_backend.models.base import Base, TimestampMixin, UUIDPKMixin


class AutomatonFolder(UUIDPKMixin, TimestampMixin, Base):
    """Self-referential (folders in folders), owned by a user. Deeper cycles
    (A -> B -> A) aren't enforceable by a simple DB constraint - only the trivial
    self-parent case is (CHECK below); deeper cycles are rejected at the
    application layer (see services/folders.py) via an ancestor walk.
    """

    __tablename__ = "automaton_folders"
    __table_args__ = (
        CheckConstraint("id <> parent_id", name="ck_automaton_folders_not_self_parent"),
        Index("ix_automaton_folders_user_parent", "user_id", "parent_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automaton_folders.id", ondelete="RESTRICT"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
