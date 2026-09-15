"""index sessions(last_seen_at, expires_at) - perf pass

services/stats.py's get_live_stats backs GET /stats/live, the home page's
"live activity" counter - deliberately unauthenticated (CLAUDE.md S2/S3), so
it's the one query in the app guaranteed to run from every visitor, logged in
or not, on a 20s poll. It filters sessions on exactly last_seen_at + expires_at,
which had no supporting index - a full table scan on every poll, on a table
this project's own history already flagged as prone to unbounded growth
(the 2026-08-30 expired-session sweep, auth/session.py:sweep_expired_sessions,
was added for the same underlying reason). last_seen_at leads the composite
since it's the more selective predicate (a 120s window, ONLINE_WINDOW_SECONDS)
vs expires_at (true for nearly every non-expired row).

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-02

"""

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_sessions_last_seen", "sessions", ["last_seen_at", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_sessions_last_seen", table_name="sessions")
