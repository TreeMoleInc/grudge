"""The two-tier friend-visibility resolution (CLAUDE.md S2). `resolve_visible_automaton_ids`
is pure/dependency-free so it's unit-testable without a DB, same philosophy as
services/folders.py's find_cycle. Everything else here is the DB-backed
plumbing around it: reading/upserting settings and overrides, and the
automaton-creation-time "share with friends" hook.
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.models.automaton import Automaton
from grudge_backend.models.friend import (
    FriendSettings,
    FriendSettingsAutomaton,
    FriendVisibilityOverride,
    FriendVisibilityOverrideAutomaton,
)

GlobalMode = Literal["show", "hide", "specific"]
OverrideMode = Literal["default", "show", "hide", "specific"]


def resolve_visible_automaton_ids(
    *,
    global_mode: GlobalMode,
    global_allow_ids: set[uuid.UUID],
    override_mode: OverrideMode,
    override_allow_ids: set[uuid.UUID],
    all_owner_automaton_ids: set[uuid.UUID],
) -> set[uuid.UUID]:
    """A per-friend override that isn't "default" fully replaces the global
    setting, even toward a narrower result (CLAUDE.md's explicit "either
    direction" wording) - "default" is the only mode that falls through to
    the global setting. `all_owner_automaton_ids` is intersected into the
    result defensively, so a stale allow-list id (one no longer owned by the
    automaton's current owner) can never leak into what's shown.
    """
    effective_mode: str = global_mode if override_mode == "default" else override_mode
    effective_allow_ids = override_allow_ids if override_mode == "specific" else global_allow_ids

    if effective_mode == "show":
        return set(all_owner_automaton_ids)
    if effective_mode == "hide":
        return set()
    if effective_mode == "specific":
        return all_owner_automaton_ids & effective_allow_ids
    raise ValueError(f"unknown effective mode: {effective_mode!r}")


class AutomataNotOwnedError(Exception):
    pass


async def assert_all_owned(
    db: AsyncSession, *, user_id: uuid.UUID, automaton_ids: list[uuid.UUID]
) -> None:
    if not automaton_ids:
        return
    result = await db.execute(
        select(Automaton.id).where(Automaton.user_id == user_id, Automaton.id.in_(automaton_ids))
    )
    owned_ids = {row[0] for row in result.all()}
    if owned_ids != set(automaton_ids):
        raise AutomataNotOwnedError("One or more of the selected automata do not belong to you.")


async def get_or_create_friend_settings(db: AsyncSession, *, user_id: uuid.UUID) -> FriendSettings:
    result = await db.execute(select(FriendSettings).where(FriendSettings.user_id == user_id))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = FriendSettings(user_id=user_id)
        db.add(settings)
        await db.flush()
    return settings


async def get_friend_settings_or_default(
    db: AsyncSession, *, user_id: uuid.UUID
) -> tuple[str, set[uuid.UUID]]:
    """Read-only - never creates a row. Every player implicitly starts at
    the "hide" default (CLAUDE.md) whether or not a settings row exists yet.
    """
    result = await db.execute(select(FriendSettings).where(FriendSettings.user_id == user_id))
    settings = result.scalar_one_or_none()
    if settings is None:
        return "hide", set()
    allow_result = await db.execute(
        select(FriendSettingsAutomaton.automaton_id).where(
            FriendSettingsAutomaton.user_id == user_id
        )
    )
    return settings.global_mode, {row[0] for row in allow_result.all()}


async def get_or_create_override(
    db: AsyncSession, *, user_id: uuid.UUID, friend_user_id: uuid.UUID
) -> FriendVisibilityOverride:
    result = await db.execute(
        select(FriendVisibilityOverride).where(
            FriendVisibilityOverride.user_id == user_id,
            FriendVisibilityOverride.friend_user_id == friend_user_id,
        )
    )
    override = result.scalar_one_or_none()
    if override is None:
        override = FriendVisibilityOverride(user_id=user_id, friend_user_id=friend_user_id)
        db.add(override)
        await db.flush()
    return override


async def get_override_or_default(
    db: AsyncSession, *, user_id: uuid.UUID, friend_user_id: uuid.UUID
) -> tuple[str, set[uuid.UUID]]:
    """Read-only - never creates a row. Every friendship implicitly starts
    at "default" (inherit global) until explicitly overridden.
    """
    result = await db.execute(
        select(FriendVisibilityOverride).where(
            FriendVisibilityOverride.user_id == user_id,
            FriendVisibilityOverride.friend_user_id == friend_user_id,
        )
    )
    override = result.scalar_one_or_none()
    if override is None:
        return "default", set()
    allow_result = await db.execute(
        select(FriendVisibilityOverrideAutomaton.automaton_id).where(
            FriendVisibilityOverrideAutomaton.override_id == override.id
        )
    )
    return override.mode, {row[0] for row in allow_result.all()}


async def get_visible_automata(
    db: AsyncSession, *, owner_user_id: uuid.UUID, viewer_user_id: uuid.UUID
) -> list[Automaton]:
    """`owner_user_id` is the friend being viewed (whose settings control the
    result); `viewer_user_id` is the current user looking. Assumes the
    caller has already confirmed the two are friends (routers/friends.py's
    profile endpoint does this itself and 404s otherwise) - this function is
    single-purpose: given a confirmed relationship, which of owner's
    automata does viewer get to see.
    """
    owner_automata = list(
        (await db.execute(select(Automaton).where(Automaton.user_id == owner_user_id)))
        .scalars()
        .all()
    )
    all_ids = {a.id for a in owner_automata}

    global_mode, global_allow_ids = await get_friend_settings_or_default(db, user_id=owner_user_id)
    override_mode, override_allow_ids = await get_override_or_default(
        db, user_id=owner_user_id, friend_user_id=viewer_user_id
    )

    visible_ids = resolve_visible_automaton_ids(
        global_mode=global_mode,  # type: ignore[arg-type]
        global_allow_ids=global_allow_ids,
        override_mode=override_mode,  # type: ignore[arg-type]
        override_allow_ids=override_allow_ids,
        all_owner_automaton_ids=all_ids,
    )
    return [a for a in owner_automata if a.id in visible_ids]


async def apply_share_with_friends(
    db: AsyncSession, *, user_id: uuid.UUID, automaton_id: uuid.UUID
) -> None:
    """The automaton-creation-time "share with friends" checkbox hook
    (CLAUDE.md S2): adds the new automaton to the global specific-allowlist
    unconditionally, and to every existing per-friend override currently in
    "specific" mode. Never touches global_mode itself, and never creates new
    override rows for friends still at "default" - only adds to allow-lists
    that already exist or are meant to always exist (the global one).
    """
    await get_or_create_friend_settings(db, user_id=user_id)
    db.add(FriendSettingsAutomaton(user_id=user_id, automaton_id=automaton_id))

    result = await db.execute(
        select(FriendVisibilityOverride).where(
            FriendVisibilityOverride.user_id == user_id,
            FriendVisibilityOverride.mode == "specific",
        )
    )
    for override in result.scalars().all():
        db.add(
            FriendVisibilityOverrideAutomaton(override_id=override.id, automaton_id=automaton_id)
        )
    await db.flush()
