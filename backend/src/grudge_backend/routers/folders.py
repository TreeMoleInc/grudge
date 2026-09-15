from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.auth.dependencies import get_current_user
from grudge_backend.db import get_db
from grudge_backend.exceptions import conflict, not_found
from grudge_backend.models.folder import AutomatonFolder
from grudge_backend.models.user import User
from grudge_backend.schemas.folder import FolderCreate, FolderRead, FolderUpdate
from grudge_backend.services.folders import (
    FolderCycleError,
    FolderNotEmptyError,
    assert_empty,
    assert_no_cycle,
)
from grudge_backend.services.ordering import next_sort_order

router = APIRouter(prefix="/folders", tags=["folders"])


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


@router.post("", response_model=FolderRead, status_code=201)
async def create_folder(
    payload: FolderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutomatonFolder:
    if payload.parent_id is not None:
        await _get_owned_folder(db, folder_id=payload.parent_id, user_id=current_user.id)

    sort_order = await next_sort_order(
        db,
        model=AutomatonFolder,
        user_id=current_user.id,
        scope_column=AutomatonFolder.parent_id,
        scope_value=payload.parent_id,
    )
    folder = AutomatonFolder(
        user_id=current_user.id,
        parent_id=payload.parent_id,
        name=payload.name,
        sort_order=sort_order,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return folder


@router.get("", response_model=list[FolderRead])
async def list_folders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AutomatonFolder]:
    # Flat list, not a nested tree - the client builds the tree client-side in
    # O(n), which sidesteps a recursive CTE server-side and doesn't force a
    # response shape on the future UI (see the Phase 2 plan for the rationale).
    result = await db.execute(
        select(AutomatonFolder)
        .where(AutomatonFolder.user_id == current_user.id)
        .order_by(AutomatonFolder.sort_order)
    )
    return list(result.scalars().all())


@router.patch("/{folder_id}", response_model=FolderRead)
async def update_folder(
    folder_id: uuid.UUID,
    payload: FolderUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutomatonFolder:
    folder = await _get_owned_folder(db, folder_id=folder_id, user_id=current_user.id)
    updates = payload.model_dump(exclude_unset=True)

    if "parent_id" in updates:
        new_parent_id = updates["parent_id"]
        if new_parent_id is not None:
            await _get_owned_folder(db, folder_id=new_parent_id, user_id=current_user.id)
        try:
            await assert_no_cycle(
                db, folder_id=folder.id, new_parent_id=new_parent_id, user_id=current_user.id
            )
        except FolderCycleError as exc:
            raise conflict(str(exc)) from exc
        folder.parent_id = new_parent_id

    if "name" in updates:
        folder.name = updates["name"]

    await db.commit()
    await db.refresh(folder)
    return folder


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    folder = await _get_owned_folder(db, folder_id=folder_id, user_id=current_user.id)
    try:
        await assert_empty(db, folder_id=folder.id, user_id=current_user.id)
    except FolderNotEmptyError as exc:
        raise conflict(str(exc)) from exc
    await db.delete(folder)
    await db.commit()
