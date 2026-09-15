from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.models.automaton import Automaton, AutomatonVersion
from grudge_backend.schemas.version import DEFAULT_VERSION_CODE
from grudge_backend.services.ordering import next_sort_order


class VersionNotOwnedByAutomatonError(Exception):
    pass


async def create_automaton_with_first_version(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    folder_id: uuid.UUID | None,
    code: str | None,
) -> tuple[Automaton, AutomatonVersion]:
    """Creates the automaton and its first version together, then wires up
    active_version_id - three statements in one transaction (caller commits).
    Uses flush(), not commit(), between steps so automaton.id/version.id are
    assigned without ending the transaction the caller controls.
    """
    sort_order = await next_sort_order(
        db,
        model=Automaton,
        user_id=user_id,
        scope_column=Automaton.folder_id,
        scope_value=folder_id,
    )
    automaton = Automaton(user_id=user_id, folder_id=folder_id, name=name, sort_order=sort_order)
    db.add(automaton)
    await db.flush()

    version = AutomatonVersion(
        automaton_id=automaton.id,
        name="v1",
        code=code if code is not None else DEFAULT_VERSION_CODE,
    )
    db.add(version)
    await db.flush()

    automaton.active_version_id = version.id
    await db.flush()

    return automaton, version


async def set_active_version(
    db: AsyncSession, *, automaton: Automaton, version_id: uuid.UUID
) -> None:
    """The FK on active_version_id only proves `version_id` exists SOMEWHERE in
    automaton_versions - it can't prove it belongs to THIS automaton, so that
    has to be checked explicitly here.
    """
    result = await db.execute(
        select(AutomatonVersion.id).where(
            AutomatonVersion.id == version_id, AutomatonVersion.automaton_id == automaton.id
        )
    )
    if result.scalar_one_or_none() is None:
        raise VersionNotOwnedByAutomatonError(
            "This version does not belong to the specified automaton."
        )
    automaton.active_version_id = version_id
    await db.flush()
