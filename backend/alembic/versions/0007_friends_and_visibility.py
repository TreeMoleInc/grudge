"""friends, friend requests, and the two-tier friend-visibility system (Phase 5)

Adds the social graph (friend_requests, friends) and the two-tier visibility
control described in CLAUDE.md S2 ("Friend visibility: confirmed two-tier
system"): a per-player global default (friend_settings + its allow-list join
table friend_settings_automata) and a per-friendship override that fully
replaces the global setting in either direction (friend_visibility_overrides
+ its allow-list join table friend_visibility_override_automata).

friend_requests has no status column and no updated_at - a row's mere
existence IS its pending state (accept/decline/cancel all DELETE it, accept
additionally inserting the friends pair in the same transaction). No unique
constraint on (from_user_id, to_user_id) either, deliberately - that's what
lets someone re-request after a decline without fighting a DB constraint;
the service layer checks for an existing pending row in either direction
before inserting a new one.

friend_settings_automata FKs directly to users.id rather than through
friend_settings.id (unlike friend_visibility_override_automata, which FKs
through its parent override's id) - the automaton-creation "share with
friends" checkbox must be able to write here unconditionally, possibly
before any friend_settings row exists for that player.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-29

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "friend_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "from_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_friend_requests_not_self", "friend_requests", "from_user_id <> to_user_id"
    )
    op.create_index("ix_friend_requests_from_user", "friend_requests", ["from_user_id"])
    op.create_index("ix_friend_requests_to_user", "friend_requests", ["to_user_id"])

    op.create_table(
        "friends",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "friend_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_check_constraint("ck_friends_not_self", "friends", "user_id <> friend_user_id")
    op.create_unique_constraint("uq_friends_user_friend", "friends", ["user_id", "friend_user_id"])

    op.create_table(
        "friend_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("global_mode", sa.String(16), nullable=False, server_default="hide"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_unique_constraint("uq_friend_settings_user", "friend_settings", ["user_id"])

    op.create_table(
        "friend_settings_automata",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "automaton_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automata.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_unique_constraint(
        "uq_friend_settings_automata_user_automaton",
        "friend_settings_automata",
        ["user_id", "automaton_id"],
    )

    op.create_table(
        "friend_visibility_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "friend_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(16), nullable=False, server_default="default"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_friend_visibility_overrides_not_self",
        "friend_visibility_overrides",
        "user_id <> friend_user_id",
    )
    op.create_unique_constraint(
        "uq_friend_visibility_overrides_user_friend",
        "friend_visibility_overrides",
        ["user_id", "friend_user_id"],
    )

    op.create_table(
        "friend_visibility_override_automata",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "override_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("friend_visibility_overrides.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "automaton_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automata.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_unique_constraint(
        "uq_friend_visibility_override_automata_override_automaton",
        "friend_visibility_override_automata",
        ["override_id", "automaton_id"],
    )


def downgrade() -> None:
    op.drop_table("friend_visibility_override_automata")
    op.drop_table("friend_visibility_overrides")
    op.drop_table("friend_settings_automata")
    op.drop_table("friend_settings")
    op.drop_table("friends")
    op.drop_table("friend_requests")
