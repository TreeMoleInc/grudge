"""Folder-tree invariants the DB can't enforce by itself: deeper cycles (only
the trivial self-parent case has a DB CHECK constraint) and "don't delete a
non-empty folder" (the DB's ON DELETE RESTRICT on the relevant FKs is a
backstop, but we want a clean 409 from the API, not a raw IntegrityError).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.models.automaton import Automaton
from grudge_backend.models.folder import AutomatonFolder


class FolderCycleError(Exception):
    pass


class FolderNotEmptyError(Exception):
    pass


ParentLookup = Callable[[uuid.UUID], Awaitable["uuid.UUID | None"]]


async def find_cycle(
    *, folder_id: uuid.UUID, new_parent_id: uuid.UUID | None, get_parent: ParentLookup
) -> bool:
    """Pure graph-walk: would setting `folder_id`'s parent to `new_parent_id`
    create a cycle? `get_parent` is injected so this algorithm can be unit-tested
    with a plain in-memory lookup (tests/unit/test_folder_cycle_logic.py), no DB
    needed - assert_no_cycle below supplies the real DB-backed lookup used in
    production, so there's exactly one implementation of the walk itself.
    """
    if new_parent_id is None:
        return False
    if new_parent_id == folder_id:
        return True

    current_id: uuid.UUID | None = new_parent_id
    seen: set[uuid.UUID] = set()
    while current_id is not None:
        if current_id == folder_id:
            return True
        if current_id in seen:
            return False  # defensive: an existing cycle shouldn't be reachable
        seen.add(current_id)
        current_id = await get_parent(current_id)
    return False


async def assert_no_cycle(
    db: AsyncSession, *, folder_id: uuid.UUID, new_parent_id: uuid.UUID | None, user_id: uuid.UUID
) -> None:
    async def get_parent(fid: uuid.UUID) -> uuid.UUID | None:
        result = await db.execute(
            select(AutomatonFolder.parent_id).where(
                AutomatonFolder.id == fid, AutomatonFolder.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    if await find_cycle(folder_id=folder_id, new_parent_id=new_parent_id, get_parent=get_parent):
        if new_parent_id == folder_id:
            raise FolderCycleError("A folder cannot be its own parent.")
        raise FolderCycleError("Moving this folder here would create a cycle.")


async def assert_empty(db: AsyncSession, *, folder_id: uuid.UUID, user_id: uuid.UUID) -> None:
    child_folder = await db.execute(
        select(AutomatonFolder.id)
        .where(AutomatonFolder.parent_id == folder_id, AutomatonFolder.user_id == user_id)
        .limit(1)
    )
    if child_folder.scalar_one_or_none() is not None:
        raise FolderNotEmptyError("This folder contains subfolders and cannot be deleted.")

    child_automaton = await db.execute(
        select(Automaton.id)
        .where(Automaton.folder_id == folder_id, Automaton.user_id == user_id)
        .limit(1)
    )
    if child_automaton.scalar_one_or_none() is not None:
        raise FolderNotEmptyError("This folder contains automata and cannot be deleted.")
