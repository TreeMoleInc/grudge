"""tournament_entries, matches, rating_history, notifications (Phase 6)

Closes the four gaps Phase 3 deliberately left open (CLAUDE.md S4's Phase 6
bullet): tournament_entries/matches are an ADDITIVE relational layer over
tournaments.entrants/result (which stay exactly as they are - the Results page
keeps reading them unchanged), so cross-tournament queries ("every match
between these two players") don't require scanning JSON. rating_history backs
the Elo update math (services/rating.py) - one row per player per ranked
tournament. notifications is the durable store for the "automaton flagged"
mechanism, which previously only reached a live-connected WebSocket viewer.

tournament_entries/matches use SET NULL (not CASCADE) on their user/automaton/
version FKs, deliberately mirroring tournaments.entrants's existing
account-deletion behavior (anonymized in place, per CLAUDE.md S2) rather than
CASCADE, which would silently let match history disappear on account deletion
- exactly what that design was built to prevent. rating_history and
notifications are private per-user records nobody else's query ever reads, so
their user_id FKs are plain CASCADE.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-30

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tournament_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tournament_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tournaments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "automaton_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automata.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "automaton_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automaton_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("code_snapshot", sa.Text(), nullable=True),
        sa.Column("rating_snapshot", sa.Integer(), nullable=False),
        sa.Column("automaton_name", sa.String(255), nullable=True),
        sa.Column("owner_username", sa.String(64), nullable=True),
        sa.Column("automaton_version_name", sa.String(255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_unique_constraint(
        "uq_tournament_entries_tournament_automaton",
        "tournament_entries",
        ["tournament_id", "automaton_id"],
    )
    op.create_index(
        "ix_tournament_entries_automaton", "tournament_entries", ["automaton_id"]
    )
    op.create_index("ix_tournament_entries_user", "tournament_entries", ["user_id"])

    op.create_table(
        "matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tournament_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tournaments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "automaton_a_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automata.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "automaton_b_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automata.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("games_played", sa.Integer(), nullable=False),
        sa.Column("score_a", sa.Integer(), nullable=False),
        sa.Column("score_b", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("voided_side", sa.String(8), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("rounds", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("ix_matches_tournament", "matches", ["tournament_id"])
    op.create_index("ix_matches_automaton_a", "matches", ["automaton_a_id"])
    op.create_index("ix_matches_automaton_b", "matches", ["automaton_b_id"])

    op.create_table(
        "rating_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tournament_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tournaments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating_before", sa.Integer(), nullable=False),
        sa.Column("rating_after", sa.Integer(), nullable=False),
        sa.Column("delta", sa.Float(), nullable=False),
        sa.Column("k_used", sa.Integer(), nullable=False),
        sa.Column("e_i", sa.Float(), nullable=False),
        sa.Column("s_i", sa.Float(), nullable=False),
        sa.Column("ranked_tournaments_played_before", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_unique_constraint(
        "uq_rating_history_tournament_user", "rating_history", ["tournament_id", "user_id"]
    )
    op.create_index("ix_rating_history_user", "rating_history", ["user_id"])

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column(
            "tournament_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tournaments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "automaton_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automata.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("automaton_name", sa.String(255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index(
        "ix_notifications_user_unread",
        "notifications",
        ["user_id"],
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("rating_history")
    op.drop_table("matches")
    op.drop_table("tournament_entries")
