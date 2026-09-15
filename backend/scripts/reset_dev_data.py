"""Dev-only helper: clears accumulated ephemeral test data (waiting rooms,
matchmaking queue entries, sim rooms + their entries/invites) without
touching real product data.

Scope is deliberately narrow and hardcoded, not "reset everything" - never
touches `automata`/`automaton_versions`/`automaton_folders`, `friends`/
`friend_requests`/friend-visibility tables, `tournaments` (ranked/unranked/sim
tournament history), `users`, or `sessions`. Waiting rooms/matchmaking queue
entries/sim rooms are pure in-progress-coordination state with no meaning
once a session ends - unlike the tables above, nothing legitimate is lost by
clearing them (see TODO.md's "No dev-data reset tooling" item this replaces).

Requires an explicit --yes flag so this can't be fat-fingered; prints exactly
what it's about to truncate first either way.

    python scripts/reset_dev_data.py           # dry run, shows row counts
    python scripts/reset_dev_data.py --yes     # actually clears them
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from grudge_backend.db import async_session_maker

_TABLES = (
    "waiting_rooms",
    "matchmaking_queue_entries",
    "sim_rooms",
    "sim_room_entries",
    "sim_room_invites",
)


async def main(*, confirmed: bool) -> None:
    async with async_session_maker() as db:
        counts = {}
        for table in _TABLES:
            result = await db.execute(text(f"SELECT COUNT(*) FROM {table}"))
            counts[table] = result.scalar_one()

        print("Ephemeral dev-data tables:")
        for table, count in counts.items():
            print(f"  {table}: {count} row(s)")

        if not confirmed:
            print("\nDry run - pass --yes to actually clear these tables.")
            return

        if not any(counts.values()):
            print("\nNothing to clear.")
            return

        await db.execute(text(f"TRUNCATE {', '.join(_TABLES)} CASCADE"))
        await db.commit()
        print("\nCleared.")


if __name__ == "__main__":
    asyncio.run(main(confirmed="--yes" in sys.argv[1:]))
