"""automaton_folders

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-28

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automaton_folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Self-referential. ON DELETE RESTRICT is a DB-level backstop matching
        # the app-level "reject delete of non-empty folder" rule.
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automaton_folders.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_automaton_folders_not_self_parent", "automaton_folders", "id <> parent_id"
    )
    op.create_index("ix_automaton_folders_user_parent", "automaton_folders", ["user_id", "parent_id"])


def downgrade() -> None:
    op.drop_table("automaton_folders")
