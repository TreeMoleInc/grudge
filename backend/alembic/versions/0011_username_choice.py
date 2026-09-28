"""player-chosen usernames: username_is_default + case-insensitive uniqueness

Enables players to rename themselves (previously fixed forever at account
creation, derived from the OAuth provider's email prefix - see
routers/auth.py's _unique_username). Two changes:

- `username_is_default`: true for every existing account (none of them was
  ever deliberately chosen - all came from that email-prefix default) and
  for every new signup; the frontend uses it to show a one-time "choose a
  username" prompt, flipped false the first time PATCH /me actually renames
  the account (services/users.py).
- The uniqueness constraint moves from a plain case-sensitive
  UNIQUE(username) (uq_users_username, migration 0001) to a case-insensitive
  functional unique index on lower(username) - "Joseph" and "joseph"
  shouldn't be able to coexist once renaming is a real, player-driven
  action, not just whatever a provider's email prefix happened to be.
  Declared directly here via raw SQL rather than in the ORM model's
  __table_args__, matching this project's existing precedent for
  expression/functional indexes (migration 0009's relational-table indexes -
  see CLAUDE.md S5's note that this model/migration gap is deliberate, not
  accidental).

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-28

"""

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("username_is_default", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.drop_constraint("uq_users_username", "users", type_="unique")
    op.execute("CREATE UNIQUE INDEX ux_users_username_lower ON users (lower(username))")


def downgrade() -> None:
    op.execute("DROP INDEX ux_users_username_lower")
    op.create_unique_constraint("uq_users_username", "users", ["username"])
    op.drop_column("users", "username_is_default")
