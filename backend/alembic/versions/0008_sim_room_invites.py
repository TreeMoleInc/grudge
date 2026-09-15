"""sim_room_invites - direct friend invites for sim rooms

Lets a sim room owner invite a specific friend directly (POST /sim-rooms/{id}/invites)
as an alternative to only sharing the invite code out-of-band. No status column -
an invite is "pending" for as long as its room stays "open"; the listing query
(GET /sim-rooms/invites) joins against still-open rooms rather than needing an
explicit status/cleanup step once a room starts.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-29

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sim_room_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sim_room_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sim_rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invited_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invited_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_unique_constraint(
        "uq_sim_room_invites_room_user", "sim_room_invites", ["sim_room_id", "invited_user_id"]
    )


def downgrade() -> None:
    op.drop_table("sim_room_invites")
