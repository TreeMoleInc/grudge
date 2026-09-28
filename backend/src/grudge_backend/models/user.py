from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grudge_backend.models.base import Base, CreatedAtMixin, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"

    # NOT unique=True here - uniqueness is enforced by a case-insensitive
    # functional index (ux_users_username_lower, migration 0011) instead of a
    # plain column constraint, so "Joseph" and "joseph" can't coexist once a
    # player can actually choose their own name. See that migration's
    # docstring for why the index itself isn't declared in this model.
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    # True until the player explicitly renames themselves via PATCH /me
    # (services/users.py) - every account starts here, since the initial
    # value is always the OAuth provider's email prefix (_unique_username in
    # routers/auth.py), never a deliberate choice. The frontend uses this to
    # show a one-time "choose a username" prompt after sign-in.
    username_is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
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
