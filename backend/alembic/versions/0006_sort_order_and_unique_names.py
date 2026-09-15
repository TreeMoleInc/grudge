"""sort_order for automata/automaton_folders + unique automaton names per user

Adds a per-sibling-group `sort_order` column to both `automata` and
`automaton_folders` (backfilled by creation order, scoped by (user_id,
folder_id/parent_id)) to back the up/down-arrow reorder feature, and a
UNIQUE(user_id, name) constraint on `automata` so two of a player's own
automata can no longer share a name.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-29

"""

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("automata", sa.Column("sort_order", sa.Integer(), nullable=True))
    op.add_column("automaton_folders", sa.Column("sort_order", sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE automata a
        SET sort_order = sub.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY user_id, COALESCE(folder_id, '00000000-0000-0000-0000-000000000000'::uuid)
                ORDER BY created_at
            ) - 1 AS rn
            FROM automata
        ) sub
        WHERE a.id = sub.id
        """
    )
    op.execute(
        """
        UPDATE automaton_folders f
        SET sort_order = sub.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY user_id, COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid)
                ORDER BY created_at
            ) - 1 AS rn
            FROM automaton_folders
        ) sub
        WHERE f.id = sub.id
        """
    )

    op.alter_column("automata", "sort_order", nullable=False, server_default="0")
    op.alter_column("automaton_folders", "sort_order", nullable=False, server_default="0")

    # Pre-existing dev/test data can already have duplicate (user_id, name)
    # pairs from before this constraint existed - disambiguate them so the
    # constraint below can actually be created, rather than requiring a
    # manual cleanup pass first.
    op.execute(
        """
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id, name ORDER BY created_at) AS rn
            FROM automata
        )
        UPDATE automata a
        SET name = a.name || ' (' || ranked.rn || ')'
        FROM ranked
        WHERE a.id = ranked.id AND ranked.rn > 1
        """
    )

    op.create_unique_constraint("uq_automata_user_name", "automata", ["user_id", "name"])


def downgrade() -> None:
    op.drop_constraint("uq_automata_user_name", "automata", type_="unique")
    op.drop_column("automaton_folders", "sort_order")
    op.drop_column("automata", "sort_order")
