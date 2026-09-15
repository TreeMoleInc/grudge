from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.auth.dependencies import get_current_user
from grudge_backend.db import get_db
from grudge_backend.exceptions import conflict, not_found
from grudge_backend.models.automaton import Automaton, AutomatonVersion
from grudge_backend.models.user import User
from grudge_backend.schemas.version import (
    DEFAULT_VERSION_CODE,
    VersionCreate,
    VersionRead,
    VersionSummary,
    VersionUpdate,
)
from grudge_backend.services.versions import (
    LastVersionError,
    VersionIsActiveError,
    assert_deletable,
)

router = APIRouter(prefix="/automata/{automaton_id}/versions", tags=["versions"])


async def _get_owned_automaton(
    db: AsyncSession, *, automaton_id: uuid.UUID, user_id: uuid.UUID
) -> Automaton:
    result = await db.execute(
        select(Automaton).where(Automaton.id == automaton_id, Automaton.user_id == user_id)
    )
    automaton = result.scalar_one_or_none()
    if automaton is None:
        raise not_found("Automaton not found.")
    return automaton


async def _get_version(
    db: AsyncSession, *, automaton_id: uuid.UUID, version_id: uuid.UUID
) -> AutomatonVersion:
    result = await db.execute(
        select(AutomatonVersion).where(
            AutomatonVersion.id == version_id, AutomatonVersion.automaton_id == automaton_id
        )
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise not_found("Version not found.")
    return version


@router.post("", response_model=VersionRead, status_code=201)
async def create_version(
    automaton_id: uuid.UUID,
    payload: VersionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutomatonVersion:
    automaton = await _get_owned_automaton(db, automaton_id=automaton_id, user_id=current_user.id)

    code = payload.code
    if code is None:
        # Forks the current active version's code as a starting point rather
        # than defaulting to blank - the natural "fork current" UX for the
        # explicit new-version action.
        code = DEFAULT_VERSION_CODE
        if automaton.active_version_id is not None:
            active = await db.get(AutomatonVersion, automaton.active_version_id)
            if active is not None:
                code = active.code

    count_result = await db.execute(
        select(AutomatonVersion.id).where(AutomatonVersion.automaton_id == automaton_id)
    )
    next_number = len(count_result.scalars().all()) + 1

    version = AutomatonVersion(
        automaton_id=automaton_id, name=payload.name or f"v{next_number}", code=code
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version


@router.get("", response_model=list[VersionSummary])
async def list_versions(
    automaton_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AutomatonVersion]:
    await _get_owned_automaton(db, automaton_id=automaton_id, user_id=current_user.id)
    result = await db.execute(
        select(AutomatonVersion).where(AutomatonVersion.automaton_id == automaton_id)
    )
    return list(result.scalars().all())


@router.get("/{version_id}", response_model=VersionRead)
async def get_version(
    automaton_id: uuid.UUID,
    version_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutomatonVersion:
    await _get_owned_automaton(db, automaton_id=automaton_id, user_id=current_user.id)
    return await _get_version(db, automaton_id=automaton_id, version_id=version_id)


@router.patch("/{version_id}", response_model=VersionRead)
async def update_version(
    automaton_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: VersionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutomatonVersion:
    await _get_owned_automaton(db, automaton_id=automaton_id, user_id=current_user.id)
    version = await _get_version(db, automaton_id=automaton_id, version_id=version_id)

    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates:
        version.name = updates["name"]
    if "code" in updates:
        version.code = updates["code"]

    await db.commit()
    await db.refresh(version)
    return version


@router.delete("/{version_id}", status_code=204)
async def delete_version(
    automaton_id: uuid.UUID,
    version_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    automaton = await _get_owned_automaton(db, automaton_id=automaton_id, user_id=current_user.id)
    version = await _get_version(db, automaton_id=automaton_id, version_id=version_id)
    try:
        await assert_deletable(db, automaton=automaton, version_id=version_id)
    except (VersionIsActiveError, LastVersionError) as exc:
        raise conflict(str(exc)) from exc
    await db.delete(version)
    await db.commit()
