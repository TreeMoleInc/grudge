from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.auth.dependencies import get_current_user
from grudge_backend.db import get_db
from grudge_backend.exceptions import not_found
from grudge_backend.models.user import User
from grudge_backend.schemas.notification import NotificationRead
from grudge_backend.services import notifications as notifications_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationRead])
async def list_notifications(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationRead]:
    return await notifications_service.list_for_user(db, user_id=current_user.id, limit=limit)


@router.post("/read-all", status_code=204)
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    await notifications_service.mark_all_read(db, user_id=current_user.id)
    await db.commit()


@router.post("/{notification_id}/read", status_code=204)
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await notifications_service.mark_read(
            db, notification_id=notification_id, user_id=current_user.id
        )
    except notifications_service.NotificationNotFoundError as exc:
        raise not_found(str(exc)) from exc
    await db.commit()
