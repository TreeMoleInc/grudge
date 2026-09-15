"""Assigns a stable creation-order `sort_order` to a new automaton/folder,
scoped to its sibling group (same user_id + folder_id/parent_id). Written
generically over any model with `user_id` and `sort_order` columns rather
than duplicated per model, since automata and automaton_folders both need it.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class _HasOrderingColumns(Protocol):
    id: Any
    user_id: Any
    sort_order: Any


T = TypeVar("T", bound=_HasOrderingColumns)


async def next_sort_order(
    db: AsyncSession, *, model: type[T], user_id: uuid.UUID, scope_column: Any, scope_value: Any
) -> int:
    result = await db.execute(
        select(model.sort_order)  # type: ignore[attr-defined]
        .where(model.user_id == user_id, scope_column == scope_value)  # type: ignore[attr-defined]
        .order_by(model.sort_order.desc())  # type: ignore[attr-defined]
        .limit(1)
    )
    highest = result.scalar_one_or_none()
    return (highest + 1) if highest is not None else 0
