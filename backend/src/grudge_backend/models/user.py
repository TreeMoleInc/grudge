from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grudge_backend.models.base import Base, CreatedAtMixin, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Informational only, populated from whichever provider first created the
    # account - deliberately NOT unique and NOT used as an identity/linking key.
    # See AuthIdentity for the actual login lookup.
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    rating: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1000, server_default="1000"
    )
    ranked_tournaments_played: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    auth_identities: Mapped[list[AuthIdentity]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthIdentity(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_auth_identities_provider_user"),
        UniqueConstraint("user_id", "provider", name="uq_auth_identities_user_provider"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    user: Mapped[User] = relationship(back_populates="auth_identities")
