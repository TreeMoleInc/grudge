"""users and auth_identities

Revision ID: 0001
Revises:
Create Date: 2026-08-28

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("avatar_url", sa.String(2048), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("ranked_tournaments_played", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_unique_constraint("uq_users_username", "users", ["username"])

    op.create_table(
        "auth_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("provider_email", sa.String(320), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_unique_constraint(
        "uq_auth_identities_provider_user", "auth_identities", ["provider", "provider_user_id"]
    )
    op.create_unique_constraint(
        "uq_auth_identities_user_provider", "auth_identities", ["user_id", "provider"]
    )


def downgrade() -> None:
    op.drop_table("auth_identities")
    op.drop_table("users")
