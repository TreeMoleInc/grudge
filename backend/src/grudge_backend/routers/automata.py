from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.auth.dependencies import get_current_user
from grudge_backend.db import get_db
from grudge_backend.exceptions import bad_request, conflict, not_found
from grudge_backend.models.automaton import Automaton
from grudge_backend.models.folder import AutomatonFolder
from grudge_backend.models.user import User
from grudge_backend.schemas.automaton import (
    AutomatonCreate,
    AutomatonCreateResponse,
    AutomatonRead,
    AutomatonUpdate,
    SetActiveVersion,
)
from grudge_backend.schemas.match_history import (
    AutomatonRecordRead,
    HeadToHeadRead,
    MatchSummaryRead,
    OpponentSummaryRead,
)
from grudge_backend.schemas.version import VersionRead
from grudge_backend.services.automata import (
    VersionNotOwnedByAutomatonError,
    create_automaton_with_first_version,
)
from grudge_backend.services.automata import set_active_version as set_active_version_service
from grudge_backend.services.match_history import (
    automaton_record,
    head_to_head_summary,
    list_opponents,
)
from grudge_backend.services.visibility import apply_share_with_friends

_DUPLICATE_NAME_DETAIL = "An automaton with this name already exists."

router = APIRouter(prefix="/automata", tags=["automata"])


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


async def _get_owned_folder(
    db: AsyncSession, *, folder_id: uuid.UUID, user_id: uuid.UUID
) -> AutomatonFolder:
    result = await db.execute(
        select(AutomatonFolder).where(
            AutomatonFolder.id == folder_id, AutomatonFolder.user_id == user_id
        )
    )
    folder = result.scalar_one_or_none()
    if folder is None:
        raise not_found("Folder not found.")
    return folder


@router.post("", response_model=AutomatonCreateResponse, status_code=201)
async def create_automaton(
    payload: AutomatonCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutomatonCreateResponse:
    if payload.folder_id is not None:
        await _get_owned_folder(db, folder_id=payload.folder_id, user_id=current_user.id)

    try:
        automaton, version = await create_automaton_with_first_version(
            db,
            user_id=current_user.id,
            name=payload.name,
            folder_id=payload.folder_id,
            code=payload.code,
        )
        if payload.share_with_friends:
            await apply_share_with_friends(db, user_id=current_user.id, automaton_id=automaton.id)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise conflict(_DUPLICATE_NAME_DETAIL) from exc
    await db.refresh(automaton)
    await db.refresh(version)
    return AutomatonCreateResponse(
        **AutomatonRead.model_validate(automaton).model_dump(),
        first_version=VersionRead.model_validate(version),
    )


@router.get("", response_model=list[AutomatonRead])
async def list_automata(
    folder_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Automaton]:
    stmt = (
        select(Automaton).where(Automaton.user_id == current_user.id).order_by(Automaton.sort_order)
    )
    if folder_id is not None:
        stmt = stmt.where(Automaton.folder_id == folder_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{automaton_id}", response_model=AutomatonRead)
async def get_automaton(
    automaton_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Automaton:
    return await _get_owned_automaton(db, automaton_id=automaton_id, user_id=current_user.id)


@router.patch("/{automaton_id}", response_model=AutomatonRead)
async def update_automaton(
    automaton_id: uuid.UUID,
    payload: AutomatonUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Automaton:
    automaton = await _get_owned_automaton(db, automaton_id=automaton_id, user_id=current_user.id)
    updates = payload.model_dump(exclude_unset=True)

    if "folder_id" in updates:
        new_folder_id = updates["folder_id"]
        if new_folder_id is not None:
            await _get_owned_folder(db, folder_id=new_folder_id, user_id=current_user.id)
        automaton.folder_id = new_folder_id

    if "name" in updates:
        automaton.name = updates["name"]

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise conflict(_DUPLICATE_NAME_DETAIL) from exc
    await db.refresh(automaton)
    return automaton


@router.delete("/{automaton_id}", status_code=204)
async def delete_automaton(
    automaton_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    automaton = await _get_owned_automaton(db, automaton_id=automaton_id, user_id=current_user.id)
    await db.delete(automaton)
    await db.commit()


@router.patch("/{automaton_id}/active-version", response_model=AutomatonRead)
async def set_automaton_active_version(
    automaton_id: uuid.UUID,
    payload: SetActiveVersion,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Automaton:
    automaton = await _get_owned_automaton(db, automaton_id=automaton_id, user_id=current_user.id)
    try:
        await set_active_version_service(db, automaton=automaton, version_id=payload.version_id)
    except VersionNotOwnedByAutomatonError as exc:
        raise bad_request(str(exc)) from exc
    await db.commit()
    await db.refresh(automaton)
    return automaton


@router.get("/{automaton_id}/stats", response_model=AutomatonRecordRead)
async def get_automaton_stats(
    automaton_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutomatonRecordRead:
    await _get_owned_automaton(db, automaton_id=automaton_id, user_id=current_user.id)
    record = await automaton_record(db, automaton_id=automaton_id)
    return AutomatonRecordRead.model_validate(record)


@router.get("/{automaton_id}/opponents", response_model=list[OpponentSummaryRead])
async def get_automaton_opponents(
    automaton_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OpponentSummaryRead]:
    await _get_owned_automaton(db, automaton_id=automaton_id, user_id=current_user.id)
    opponents = await list_opponents(db, automaton_id=automaton_id)
    return [OpponentSummaryRead.model_validate(o) for o in opponents]


@router.get(
    "/{automaton_id}/head-to-head/{opponent_automaton_id}",
    response_model=HeadToHeadRead,
)
async def get_automaton_head_to_head(
    automaton_id: uuid.UUID,
    opponent_automaton_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HeadToHeadRead:
    # Only the caller's own automaton needs ownership-checking - the opponent
    # can belong to anyone, same as any other match-history view (this mirrors
    # a tournament Results page, which already shows opponents' automaton
    # names/code snapshots regardless of who owns them).
    await _get_owned_automaton(db, automaton_id=automaton_id, user_id=current_user.id)
    summary = await head_to_head_summary(
        db, automaton_id=automaton_id, opponent_automaton_id=opponent_automaton_id
    )
    return HeadToHeadRead(
        opponent_automaton_id=summary.opponent_automaton_id,
        opponent_name=summary.opponent_name,
        opponent_owner_username=summary.opponent_owner_username,
        wins=summary.wins,
        losses=summary.losses,
        ties=summary.ties,
        voided_matches=summary.voided_matches,
        matches=[MatchSummaryRead.model_validate(m) for m in summary.matches],
    )
