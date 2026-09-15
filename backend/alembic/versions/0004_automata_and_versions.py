"""automata and automaton_versions (circular FK)

automata.active_version_id -> automaton_versions.id, and every version's
automaton_id -> automata.id. Sequenced as: create automata with
active_version_id as a plain column (no FK yet, since automaton_versions
doesn't exist) -> create automaton_versions with its FK to automata -> add the
deferred active_version_id FK now that automaton_versions exists.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-28

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automata",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "folder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automaton_folders.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("active_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("ix_automata_user_folder", "automata", ["user_id", "folder_id"])

    op.create_table(
        "automaton_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "automaton_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automata.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("ix_automaton_versions_automaton", "automaton_versions", ["automaton_id"])

    op.create_foreign_key(
        "fk_automata_active_version_id",
        "automata",
        "automaton_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_automata_active_version_id", "automata", type_="foreignkey")
    op.drop_table("automaton_versions")
    op.drop_table("automata")
