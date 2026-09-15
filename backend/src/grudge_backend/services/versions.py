"""Version-deletion invariants: can't delete an automaton's only remaining
version (every automaton needs at least one) or its current
active_version_id (would leave that FK dangling - the player must set a
different version active first).

Safe with respect to tournament history, resolving the open question logged
in TODO.md: `code_snapshot` on a tournament's entrants is a plain string
copy taken at tournament-start time (see
services/tournaments.py:create_tournament_and_enqueue), not a live reference
to automaton_versions.id - there is no FK from tournaments to
automaton_versions, so deleting a version never touches a past match record.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.models.automaton import Automaton, AutomatonVersion


class VersionIsActiveError(Exception):
    pass


class LastVersionError(Exception):
    pass


async def assert_deletable(
    db: AsyncSession, *, automaton: Automaton, version_id: uuid.UUID
) -> None:
    if automaton.active_version_id == version_id:
        raise VersionIsActiveError(
            "Cannot delete the active version. Set a different version active first."
        )

    count_result = await db.execute(
        select(AutomatonVersion.id).where(AutomatonVersion.automaton_id == automaton.id)
    )
    if len(count_result.scalars().all()) <= 1:
        raise LastVersionError("Cannot delete an automaton's only version.")
