from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from grudge_backend.models.base import Base, TimestampMixin, UUIDPKMixin


class Automaton(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "automata"
    __table_args__ = (
        Index("ix_automata_user_folder", "user_id", "folder_id"),
        UniqueConstraint("user_id", "name", name="uq_automata_user_name"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automaton_folders.id", ondelete="RESTRICT"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Stable creation-order position among siblings sharing the same
    # (user_id, folder_id) - assigned once at creation (services/ordering.py),
    # not user-editable (an up/down reorder UI was tried and dropped).
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Circular reference with AutomatonVersion.automaton_id below. `use_alter`
    # tells SQLAlchemy's own DDL machinery to create this specific FK via a
    # deferred ALTER TABLE once automaton_versions exists - mirrors how the
    # Alembic migration sequences the same two tables (see alembic/versions/
    # 0004_automata_and_versions.py).
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "automaton_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_automata_active_version_id",
        ),
        nullable=True,
    )


class AutomatonVersion(UUIDPKMixin, TimestampMixin, Base):
    """`updated_at` (from TimestampMixin) bumping on every edit is what "mutable
    save-slot, not immutable snapshot" (CLAUDE.md §2) means at the DB level.
    """

    __tablename__ = "automaton_versions"
    __table_args__ = (Index("ix_automaton_versions_automaton", "automaton_id"),)

    automaton_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automata.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
